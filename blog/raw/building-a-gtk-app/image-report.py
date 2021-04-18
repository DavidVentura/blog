from PIL import Image, ImageDraw, ImageFont

# convert -density 2200 -resize 500x-1 -background white $file domain-aho-corasick.png

benches = [
    {
        "data": [
            ("domain-aho-corasick.png", "Aho-Corasick"),
            ("domain-bytes.png", "Bytes Trie"),
            ("domain-string.png", "String Trie"),
        ],
        "output": "../../html/images/benchmarks-domain.png",
    },
    {
        "data": [
            ("fragment-aho-corasick.png", "Aho-Corasick"),
            ("fragment-Substr.png", "rust contains"),
            ("fragment-Substr bytes.png", "window-bytes"),
            ("fragment-twoway bytes.png", "twoway bytes"),
            ("fragment-twoway u8.png", "twoway str"),
        ],
        "output": "../../html/images/benchmarks-fragment.png",
    },
]

# This assumes all images have the same size
graphs_per_row = 2
for bench in benches:
    images = []
    total_width = 0
    title_height = 40
    row_height = 0
    for idx, (fname, title) in enumerate(bench["data"]):
        img = Image.open(fname)
        images.append(img)
        total_width = img.width * graphs_per_row

        row_height = img.height + title_height
    height = row_height * (len(images) // graphs_per_row + 1)
    canvas = Image.new("RGBA", (total_width, height), color=(255, 255, 255, 0))
    acc_width = 0
    for idx, img in enumerate(images):

        label = bench["data"][idx][1]

        draw = ImageDraw.Draw(canvas)
        font = ImageFont.truetype("FreeMono.ttf", 20)

        row = idx // graphs_per_row
        w, h = draw.textsize(label)
        base_y = row_height * row + title_height
        target_x = int((img.width / 2 + acc_width) - w / 2)
        target_y = int((title_height / 2 - h / 2) + base_y - title_height)

        # mask out alpha bytes
        canvas.paste(img, box=(acc_width, base_y)) #, mask=img.split()[3])

        draw.text((target_x, target_y), label, fill=(0, 0, 0, 255), font=font)
        acc_width += img.width
        if (idx -1)% graphs_per_row == 0:
            acc_width = 0

    canvas.save(bench["output"])
