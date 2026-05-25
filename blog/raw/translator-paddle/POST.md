---
title: Improving OCR quality on the translator
date: 2026-05-25
tags: android, ocr
slug: mobile-translator-ppocr
description: signs and menus in shambles
incomplete: true
series: On-device translation for Android
---

On the previous post, we got OCR "working", in quotes, because it does not tolerate silly things like 
slight rotation, perspectives, non-book fonts or even (very) bold text. If the image was not a screenshot or a book scan, then it'd basically not work.

I'd seen that there are models, such as [PaddlePaddle OCR](https://github.com/PADDLEPADDLE/PADDLEOCR) which supposedly work _much_ better, thanks to ✨AI✨.

Though my initial experience was that it.. didn't really work.

<center>
![](assets/input.jpg)
</center>

This image, processed as-is returns... bad matches.

## Understanding the failure

The Paddle models run in two steps; first, there is a _detection_ model that outputs a heatmap of different areas
which are _likely_ to contain text. If we overlay the heatmap:

<center>
![](assets/heatmap.jpg)
</center>

So far, it looks pretty good.

The second step in the pipeline is to run a _recognizer_ model, which, given a 48px tall image, it will output the text it recognized.


<center>
![](assets/recognize-nodeskew.jpg)
</center>

As you can see it does... something. But it's obviously not right.

The first, and quite silly, problem I had was due to feeding the bounding box of the contour as the input image; yes, it does technically
contain text, but for text that is rotated/in perspective, the box is mostly whitespace.

<center>
![](assets/boxes.jpg)
</center>

<center>
![](assets/bbox-strips_box-001.jpg)
</center>

We have this arbitrarily rotated text, how do we straighten it?

Well, the detection model returns a mask, which we run through `imageproc::find_contours` to get its outline, then do [principal component analysis](https://en.wikipedia.org/wiki/Principal_component_analysis) on the outline points.

PCA gives us two perpendicular axes: one along the direction the points spread most (the reading direction), and a second one, perpendicular to it.

<center>
![](assets/PCA.png)
</center>


To straighten the image, we map each pixel of a new upright rectangle back to the original: a pixel at offset `(sx, sy)` in the new image comes from `centroid + sx*PC1 + sy*PC2` in the original, where PC1/PC2 are the two axis vectors.


<center>
![](assets/deskewed_box-001.jpg)
</center>

now, when running recognize, it works properly.
<center>
![](assets/recognize-deskew.jpg)
</center>

Before, we did a basic mapping, which can only rotate/slide the image; it can't describe changes in perspective.

What does describe perspective changes is a [homography](https://en.wikipedia.org/wiki/Homography_(computer_vision)): a single 3 by 3 matrix that maps one flat plane onto another, covering rotation, scale, shear and perspective foreshortening.

Because we know the four corners of the document (the user can pick them on the UI), and we know the target points (a rectangle), we can solve the equation to get H (the 3x3 matrix).

Given `H`, it's the same idea as before, for each pixel `(sx, sy)` of a clean output rectangle, we map it back to the original via `H * (sx, sy, 1)`, which gives a result `(x', y', w')`; the source pixel is `(x'/w', y'/w')`.

The division by `w'` is the part the basic mapping didn't have, `w'` is different per-pixel, so the far side of the document shrinks more than the near side.


So, we let the user pick corners (a bit of sloppiness is fine)

<center>
![](assets/corners.jpg)
</center>

And the image can be made pretty much fronto-parallel:
<center>
![](assets/dewarp.jpg)
</center>

and a single-box crop is now much higher quality (see how the `D` is not tilted right?)
<center>
![](assets/dewarp-strips_box-000.jpg)
</center>

While a user can manually pick the 4 corners of their image, I found this [DocAligner](https://github.com/DocsaidLab/DocAligner) model which,
most of the time, can propose the correct 4 corners of the image, and the user just needs to accept.


### Beyond rectangles

Guess what, round stuff exists! And people put labels on it. Insanity.

When scanning a bottle, there's no 'deskewing' or 'quadrilateral perspective adjustment' that will help, the whole thing is bent! I have proof!

<center>
![](assets/bendy_heatmap.jpg)
</center>


The previous deskew was based on a single principle: the text runs along a straight line, so PCA was enough to describe it. Bottles break that, the text curves, there's no single axis to follow.

So we keep the PCA rotation, but swap the straight axis for a curved one in that rotated frame. We take every contour point and fit the single parabola that passes as close as possible to all of them; that curve is the spine of the text.

The beauty of this is that a flat label needs no special case: its spine just comes out straight.

This spine is conceptually a curved version of PC1. So, it's the same mapping as the deskew, with the spine's curve added to the 
perpendicular step. The deskew was `centroid + sx*PC1 + sy*PC2`; here a pixel `(sx, sy)` comes from `centroid + sx*PC1 + (sy + spine(sx))*PC2`, where `spine(sx)` is how high the curve sits at that column. 

<center>
![](assets/bendy_bbox-strips_box-001.jpg)
</center>

becomes

<center>
![](assets/bendy_deskewed_box-001.jpg)
</center>

## Hiccups

I have this sign we bought at a flea market many years ago:

<center>
![](assets/cyrillic.jpg)
</center>

The model was consistently reading it as 

```
ВНИМАНИЕ
ВИСОКО НАПРЕЖЕНИЕ
ОПAСНО ЗА ЖИBOTA
```

and translating it as

```
ATTENTION
HIGH TENSION
OPUS FOR ZHIBOTA
```

why does the last line not work? turns out that the last line there are ASCII `A` `O` and `B` instead of the correct cyrillic letters.

Unicode keeps a [confusables](https://www.unicode.org/Public/security/8.0.0/confusables.txt) list for exactly this reason.
For now, I've filtered it down to a subset (confusable with latin letters) and applied a heuristic:

If the latin letter is surrounded by non-latin letters, and the latin letter is a confusable, replace with the script-appropriate version.

## Automatic language mode

When using tesseract, you need a model file per language. With Paddle OCR, it's one per _script_ (as in, Latin, Cyrillic, Korean, ...).

Still, to know which model to use, we can use [_another_ model]() that does script recognition; then, if we have the right model available,
run recognition through that.

With the recognized text, we still don't really know which language it is ("Hola, cómo está?" and "Hello, how are you?" are both Latin), so we can run it
through the pre-existing CLD2, guess the language, and run the translation with that source.

It's a small extra load, in a specific mode, but it is quite nice. For example, when visiting Brussels, a lot of signs are in either (or both!) Dutch and French. This mode worked well.


## Layouts are hard

When translating, if we do line-by-line translation, it's weird. The unit for the translation models is a sentence, and without, it loses track
of important context (fair, it's literally not present in its data).

The problem, is that we don't really know, given a picture, which lines should be joined or not.

I made some heuristics as I was scanning stuff around my house, things like:

- Lines which are tight together and of similar width are probably in a paragraph
- Vertical gaps between lines of >2.4x line-height are paragraph breaks
- If a line is succeded by another and the ratio of their heights is large, then the first one was a heading

but obviously this breaks. I added carve-outs for things that look like menus (prices are right-aligned? always? sometimes?)

I think the real answer is to use something like a layout model, but I couldn't find anything _small_. Most models operate on the image, and are not suitable for this application.

I found [this paper](https://arxiv.org/pdf/2304.11810.pdf) ([with this repo](https://github.com/NormXU/Layout2Graph)) which talks about computing the layout based on geometry only, so it should be extremely fast. However, they did not release the actual model/weights, and I'm not sure how to replicate it.

## Performance

Even if tesseract is not very good, it is 'quite fast' - on my initial tests, it was about 2-3x faster than the naive PP OCR pipeline.

The first, easy win was to quantize the model. Performing the math on FP32 has higher precision than necessary, and moving to FP16 reduced compute time by ~30%.

Then, the time to run inference on the detection model scales with pixel count. I was passing the original image to the model, but it is able to detect text down to a
very small scale, so capping the image to 900px on its largest side worked pretty well, and moved detection ~300ms->~100ms.

The recognition model also scales on strip _width_ (...obviously). Because this step is parallelized, having 1 long strip can hold up the entire pipeline.
A good way to ensure no single strip is 'too wide' is to cap the max-width, by splitting on spaces.

TODO SPACE ALGO

