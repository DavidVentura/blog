---
title: Live image/video translation
date: 2026-06-12
tags: android, ocr, cv
slug: mobile-translator-video
description: Lens who?
series: On-device translation for Android
---

In the previous post, we got some high quality image translation, running reasonably fast, on-device.

We can push it further though, and avoid the need to take a picture, select it, and translate in discrete steps.

This post contains a bunch of jittery video, you might get motion-sick 🙃.

As a starting point, running a screenshot full of text _on my phone_ takes:

- Detection at 1400x3200: 500ms
- Recognition: 1.5s

As usual, there are some easy tweaks that can give a large speed boosts.

First, the detection model scales linearly with pixel count and is _quite_ resilient to noise. So we can shrink the image as much as possible[^pix-budget] and get it to run in ~80ms.

[^pix-budget]: I picked 650k pixels as my budget, seemed fine. 0.14x the pixel count of the full size screenshot.

Then, the recognition model can be quantized. The published version uses `fp32` for its calculations, and it can be quantized to either `fp16` or `int8`, both of which have instructions that accelerate common operations at the hardware level ([sdot](https://developer.arm.com/documentation/ddi0596/2020-12/SIMD-FP-Instructions/SDOT--vector---Dot-Product-signed-arithmetic--vector--) and [fp16](https://developer.arm.com/documentation/101754/0624/armclang-Reference/Other-Compiler-specific-Features/Supported-architecture-features/Floating-point-extensions)). By quantizing to int8, the same screenshot executes in ~1200ms.

While this is a huge win for low effort, this brings us down to ~1.3s, which is not fast enough.

But that ~1.3s is for a screenshot _packed_ with text. Recognition scales with the amount of text (obviously, more text = more to recognize), so for small sign it should finish in 50~100ms, which is good enough to try out a live overlay:

<center>
<video controls>
    <source src="assets/first-h-2.mp4" />
</video>
</center>

I spent a long while here, trying to match contours across frames but the heatmap from the detection model is not stable... and even if it was, inference is not fast enough to run on every frame.

So, we need a different way to track scene movement, which has the upside that we only need to run detection/recognition/translation _once_, on an initial "anchor" frame.

Given that we want to translate text, and text is usually on some kind of plane (a sign, paper, etc), we saw in the previous post that there's a single [Homography](https://en.wikipedia.org/wiki/Homography_(computer_vision)) that can express the exact transformation between two planes.

We can take this homography and apply it to the translated overlay, warping it the same way the scene has moved relative to the anchor.

How do we get there though?

Detect some [image features](https://en.wikipedia.org/wiki/Feature_(computer_vision)) using [FAST](https://en.wikipedia.org/wiki/Features_from_accelerated_segment_test), which is a "corner" detecting algorithm.

Then, describe the surroundings of each feature using [rotated BRIEF](https://sites.cc.gatech.edu/classes/AY2024/cs4475_summer/images/ORB_an_efficient_alternative_to_SIFT_or_SURF.pdf), which is a way of converting the neighbors of the feature into a bunch of bits in a way that is rotation invariant and cheap to compare.

This gives us features + surroundings _on the anchor_, but some time has passed, and we now have a new, slightly different frame.

To match features between the two frames, we compare each of the new features to each of the original features, if we find a [good match](https://en.wikipedia.org/wiki/Scale-invariant_feature_transform#Keypoint_matching) then we know how the single feature has transformed, otherwise, ignore the new feature.

From the surviving matches, we can apply [RANSAC](https://en.wikipedia.org/wiki/Random_sample_consensus) to fit a Homography: try matches at random and see how many agree to the proposed homography, keep the one with the most agreements.

The first version of this was almost like a miracle

<center>
<video controls>
    <source src="assets/almost-working.mp4" />
</video>
</center>

It's still jittery though. Due to motion and sensor noise, FAST finds slightly different corners each frame, so each frame's homography gets fit from a different set of matches, and the resulting transform wobbles.

But we don't need to start from scratch on every frame, these frames are consecutive samples of a video stream, so we can use the temporal/spatial continuity between them to refine the feature search.

The [Lucas-Kanade](https://en.wikipedia.org/wiki/Lucas%E2%80%93Kanade_method) algorithm can carry confirmed matches from frame N to frame N+1 through optical flow ("seems like everything moved left, search for the features to the left").

Similarly, instead of computing a new homography per frame, we can use an [Extended Kalman Filter](https://en.wikipedia.org/wiki/Extended_Kalman_filter) to merge the new proposed H with the previous one, using different merge coefficients per degree of freedom (translation, perspective, rotation, ...).

With these new algorithms, the homography is stable over consecutive frames:

<center>
<video controls>
    <source src="assets/pinned.mp4" />
</video>
</center>

This works _amazingly well_, if a bit slow.

To make it faster, we have two phases to optimize, the single-shot detection/recognition/translation (inference), and the continuous homography tracking+overlay rendering.

## Improving inference performance

We already discussed quantization and scaling, another easy win was to replace the translation engine ([marian-nmt](https://github.com/marian-nmt/marian-dev) &rarr; [slimt](https://github.com/DavidVentura/slimt)) which is ~4x faster, leaving recognition as the main bottleneck.

To improve the wall-clock time of the recognition model, we use 4 parallel sessions which work in batches; the problem here is that some lines are much wider than others, causing the whole batch to be delayed by the longest strip.

A good way to ensure no single strip is 'too wide' is to cap the max-width, by splitting on spaces. Spaces are cheap to compute: per dewarped strip, find lines perpendicular to reading direction in which there's no sharp contrast (text usually has sharp contrast to its background).

Then, I profiled the detection model and noticed it spent 25% of its time in upsampling layers, this is only useful to make the box geometry smoother, but it's not really valuable for this app, so I dropped these two layers.

## Improving tracking performance

The continuous overlay warping+rendering went through many phases of optimization, mostly because my initial solution was extremely naive.

The overlay was initially rendered on CPU, taking about ~15ms per frame just to blit. Moving it to be an OpenGL texture, and doing the warping+blitting on GPU made it 0.3ms.

Then, the actual FAST+BRIEF+RANSAC was taking ~10ms per frame, which was fine on my (old) phone, but on a Pixel 3a (even older) it took ~35ms, which is more than the 30fps frame budget.

Turns out, that once we have a high quality set of descriptors, we can get by for a few frames with just KLT+EKF, so I moved the expensive FAST+BRIEF+RANSAC to execute asynchronously, resetting the accumulated drift every time it runs.

With the tracking executed async, even the Pixel 3a can run at 30fps.

## Improving perceived performance

The videos so far were carefully cropped to show the tracking after the detection/recognition/translation steps.

Those steps are not _too_ slow, but the user does not have any idea if the app is working at all, there's no progress indication:

<center>
<video controls>
    <source src="assets/first_translation.mp4" />
</video>
</center>

Here it takes 1.5 seconds between the tracker locking on and the translation showing on screen.

We can do two things to make this _seem_ faster; show the detection boxes ("text seems to be here") _and_ stream the text as it's recognized/translated:

<center>
<video controls>
    <source src="assets/streamed_translation.mp4" />
</video>
</center>

Here, the detection boxes show up ~200ms after the tracker locks; recognition+translation did not speed up, but it _feels_ much more responsive.

## Just getting lucky

By the time I was finishing this section, PaddlePaddle released the [v6 models](https://arxiv.org/pdf/2606.13108), which are about twice as fast. My existing optimizations continue to work, it just lowers the inference time of what was left. Easy win.

<center>
<video controls>
    <source src="assets/v6_translation.mp4" />
</video>
</center>

Detection runs in 90ms and the recognition+translation in 900ms.

## Bonus: screen translation

If we already have all these tricks to work on the camera.. can it also work on translating the screen?

Kind of. The homography trick works on a plane, is the screen a plane? Sometimes! If you are scrolling a website, it is. Content only shifts up and down; there's no rotation or perspective.

But if you are watching a video.. the subtitles are on a plane and the content is on another. What should be tracked? Definitely don't make the subtitles pan horizontally following the camera pan!

So, okay, for the screen we drop the homography and pin the overlay in place.

There is a big problem though: on Android you capture the _display output_, including your own overlays! After rendering the first frame of the overlay, the app goes into a loop of capturing and translating itself.

The first idea I had was to make the overlay semi-transparent, then, some of the underlying content can be seen, and if we subtract our (known) overlay, we would be left with only the original content. However, this compresses the original signal dramatically, making detection/recognition not really reliable.

Thinking about it, transparency means every pixel is partially see-through. What if instead we made a few pixels _fully_ see-through and the rest fully opaque? The average looks the same, but the see-through pixels carry the underlying content unmodified.

This is interesting, because modern phones have ridiculously high pixel densities.

My phone's screen is ~160mm tall, while displaying at a resolution of 1440x3216. This means each pixel is roughly, 50µm x 50µm (or 2 mils, if you are from the land of the free).

What if, we define a grid of 1x1 pixel 'holes' in the overlay, and observe the world through that? It'd be the equivalent of a nearest-neighbor downscale of the original image.

To the user, it could look something like this

<center>
![](assets/dots-shifted.png)
</center>

and the view through the overlay looks like this (pinholes are only placed on the text body, not on the pills):

<center>
![](assets/pinholes.png)
</center>

The see-through view is not good enough to run text detection/recognition, though it feels like it should be. I can definitely read under it. But when it's not perfect contrast, it gets murky.

What we can do is watch through those holes: when the content under an overlay changes, drop _that specific overlay_, recapture the area, and run it through the pipeline again.

An example, which drops & re-renders the overlays as subtitles change:
<center>
<video controls>
    <source src="assets/screen-1.mp4" />
</video>
</center>

## Fast and dull

I have mixed feelings about this part of the project. The _whole_ of the homography tracking was written by a friendly robot. Doing this by myself would've taken something like 2~6 months, but I'd probably not even started it. This took exactly 2 _weeks_.

During these two weeks, I was spoon fed information about existing literature, how it can be combined to do what I want, things I need to consider carefully, etc.

It felt like having someone with infinite patience answer all my questions.

The weird part, was that after getting an idea of how everything would fit together, I did not implement it myself.

This felt like giving projects to juniors/interns at work. Give them a task, they come up with some result which maybe behaves right, but even a quick skim of the decisions raises flags (allocating and copying a 16MB bitmap every frame???)

At the same time, it's _not_ like giving a project to someone else. Then, it'd be clear that someone else built it, and I just guided them to get there. Did _I_ build this? I definitely spent 2 weeks in front of my screen and made a lot of implementation decisions.

It's empowering and depressing at the same time.

I've never learned or gotten results so fast, however, most of the work is to sit there micromanaging a computer, waiting 15 minutes between actions.

Moving fast while going insane from boredom.

This combination of learning, boredom, speed and micromanagement falls into a bucket I have no name for.

