from PIL import Image, ImageDraw, ImageFont
import numpy as np
import reportlab.lib.pagesizes as pagesizes
import os
import re 
from PyPDF2 import PdfMerger

from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as ReportLabImage
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import pathlib
import os
import argparse
import PIL

import sys
import locale

print(f"Default encoding: {sys.getdefaultencoding()}")
print(f"Locale encoding: {locale.getpreferredencoding()}")

from PIL import __version__ as PILLOW_VERSION

print(f"Pillow version: {PILLOW_VERSION}")

_reader = None

try:
    pdfmetrics.registerFont(TTFont('ArialUnicodeMS', 'arial-unicode-ms.ttf')) 
    DEFAULT_FONT = 'ArialUnicodeMS'
except Exception as e:
    print(f"Warning: Font registration failed: {e}. Using default ReportLab font.")
    DEFAULT_FONT = 'Helvetica' 

def process_directory(image_dir, output_dir):
    """Process all image files in a directory."""
    for root, _, files in os.walk(image_dir):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                img_path = os.path.join(root, file)
                img_to_pdf(img_path, output_dir)

def combine_pdfs(pdf_files, output_path):
    """Combine multiple PDF files into a single PDF."""
    merger = PdfMerger()
    for pdf in pdf_files:
        merger.append(pdf)
    merger.write(output_path)
    merger.close()

def draw_bounds_before_process(img_path, output_dir):
    global _reader
    if _reader is None:
        from easyocr import Reader
        _reader = Reader(['sv', 'en'], model_storage_directory=pathlib.Path('./model').resolve())

    try:
        image = Image.open(img_path, exif=None).convert('RGB')
    except TypeError:
        
        image = Image.open(img_path).convert('RGB')
        try:
            import PIL.ImageOps
            image = PIL.ImageOps.exif_transpose(image) 
        except AttributeError:
            print("Warning: PIL.ImageOps.exif_transpose not available. Image rotation might not be corrected.")

    image_np = np.array(image)

    results = _reader.readtext(image_np)
    
    draw = ImageDraw.Draw(image)

    for (bbox, text, prob) in results:
        top_left = tuple(map(int, bbox[0]))
        top_right = tuple(map(int, bbox[1]))
        bottom_right = tuple(map(int, bbox[2]))
        bottom_left = tuple(map(int, bbox[3]))
        draw.line([top_left, top_right, bottom_right, bottom_left, top_left], width=2, fill='red')

        try:
            font = ImageFont.truetype("arial.ttf", size=16) 
        except IOError:
            font = ImageFont.load_default()

        draw.text(top_left, text, fill='blue', font=font)

    img_filename = os.path.basename(img_path)
    name, ext = os.path.splitext(img_filename)
    output_path = os.path.join(output_dir, f"{name}_detect{ext}")
    image.save(output_path)
    
    print(f"Detection visualized image saved to: {output_path}")

def img_to_pdf(img_path, output_dir):
    global _reader

    if _reader is None:
        from easyocr import Reader
        _reader = Reader(['sv', 'en'], model_storage_directory=pathlib.Path('./model').resolve())

    try:
        image_pil = Image.open(img_path, exif=None)
    except TypeError:
        image_pil = Image.open(img_path)
        try:
            import PIL.ImageOps
            image_pil = PIL.ImageOps.exif_transpose(image_pil)
        except AttributeError:
            print("Warning: PIL.ImageOps.exif_transpose not available.")

    image_pil.save(img_path)
    print(f"DEBUG: Overwrote original image file with EXIF-corrected version: {img_path}")
    
    image_np = np.array(image_pil)
    img_width, img_height = image_pil.size

    results = _reader.readtext(image_np)

    with open(file=os.path.join(output_dir, 'text.txt'), mode='w', encoding="utf-8") as f:
        for (bbox, text, prob) in results:
            f.write(text.encode("utf-8").decode('utf-8') + '\n')
    
    # Pass the text results to the name extraction function
    texts = [text for (bbox, text, prob) in results]
    names = extract_key_details(texts)
    
    print(f"Names detected: {names}")

    with open(file=os.path.join(output_dir, 'names.txt'), mode='w', encoding="utf-8") as f:
        for name in names:
            f.write(name.encode("utf-8").decode('utf-8') + '\n')
    
    results.sort(key=lambda res: (res[0][0][1], res[0][0][0]))

    pdf_filename = os.path.basename(img_path)
    name, ext = os.path.splitext(pdf_filename)
    output_pdf_path = os.path.join(output_dir, f"{name}.pdf")

    c = canvas.Canvas(output_pdf_path, pagesize=(img_width, img_height)) 

    c.drawImage(img_path, 0, 0, width=img_width, height=img_height)

    linked_text_objects = []
    last_text_label_name = None

    for i, (bbox, text, prob) in enumerate(results):
        
        x_min = min([coord[0] for coord in bbox])
        x_max = max([coord[0] for coord in bbox])
        y_min = min([coord[1] for coord in bbox])
        y_max = max([coord[1] for coord in bbox])

        text_label_name = f"textlabel_{i}"

        
        reportlab_y = img_height - y_max 
        text_height = y_max - y_min 

        c.setFillAlpha(0)
        font_size = max(8, int(text_height * 0.8)) 
        c.setFont(DEFAULT_FONT, font_size) 

        textobject = c.beginText()
        textobject.setTextOrigin(x_min, reportlab_y) 
        textobject.textLine(text) 

        c.drawText(textobject)

        if last_text_label_name:
            # eventually link text labels for reading order
            # need to detect text boxes individually and derive layout from that
            pass

        last_text_label_name = text_label_name
    
    c.save()
    print(f"PDF with transparent text labels saved to: {output_pdf_path}")

def includes_acronym(string):
    return re.search(r'\b[A-ZÅÄÖ]{2,}(\.[A-ZÅÄÖ]{2,})*\b', string) is not None

def includes_hyphenated_name(string):
    return re.search(r'\b[A-ZÅÄÖ][a-zåäö]+-[A-ZÅÄÖ][a-zåäö]+\b', string) is not None

def is_name(text) -> bool:
        
        without_special_chars = ''.join([c for c in text if c.isalnum() or c in 'åäö-'])
        
        if len(without_special_chars) < 2:
            return False
        
        return without_special_chars[0].isupper() and text[1:].islower()

def includes_year(string):
    return re.search(r'\b\d{4}\b', string) is not None

def extract_key_details(results: list[str]) -> list[str]:
    strategies = [
        includes_acronym,
        includes_hyphenated_name,
        includes_year,
        is_name,
    ]

    names = []

    for (bbox, text, prob) in results:
        result = None

        for strategy in strategies:
            if strategy(text):
                result = text
                break
        
        if result:
            names.append(result)

    return names

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert image to PDF with transparent text labels.")
    parser.add_argument("--output_dir", type=str, help="Directory to save the output PDF file.", default=pathlib.Path('./output').resolve())
    
    test_group = parser.add_mutually_exclusive_group()
    test_group.add_argument("--test-name-detect", type=str, help="Only the name extraction on the input text file.")

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--image_path", type=str, help="Path to the input image file.", default=None)
    input_group.add_argument("--image_dir", type=str, help="Directory containing input image files.", default=None)
    
    args = parser.parse_args()

    if args.test_name_detect:
        path = pathlib.Path(args.test_name_detect)
        with open(path, 'r') as f:
            texts = f.read().encode("utf-8").decode('utf-8').splitlines()
            names = extract_key_details(texts)
            print(f"Names detected: {names}")
    else:
        if args.image_path:
            img_to_pdf(args.image_path, args.output_dir)
        elif args.image_dir:
            process_directory(args.image_dir, args.output_dir)