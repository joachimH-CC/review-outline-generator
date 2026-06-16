"""
Extract text and images from PDF files.
Usage: python extract_pdf.py <pdf_file_or_dir> <output_text_dir> <output_image_dir>
Requires:
  pip install PyPDF2 pdfminer.six pdf2image Pillow PyMuPDF pypdfium2
  pdf2image page rendering also needs Poppler installed and available on PATH.
  On Windows, prefer installing a Poppler build separately instead of relying on pip alone.
"""
import os
import sys


def extract_pdf_text(pdf_path):
    """Extract text from PDF using PyPDF2, then PyMuPDF as a fallback."""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(pdf_path)
        pages = []
        for i, page in enumerate(reader.pages, 1):
            text = page.extract_text()
            if text and text.strip():
                pages.append(f"--- Page {i} ---\n{text.strip()}")
        if pages:
            return pages
    except ImportError:
        print("[pdf] PyPDF2 not available, install: pip install PyPDF2")
    except Exception as e:
        print(f"[pdf] PyPDF2 text extraction failed: {e}")

    try:
        import fitz
        doc = fitz.open(pdf_path)
        pages = []
        for i, page in enumerate(doc, 1):
            text = page.get_text("text")
            if text and text.strip():
                pages.append(f"--- Page {i} ---\n{text.strip()}")
        doc.close()
        if pages:
            return pages
    except ImportError:
        print("[pdf] PyMuPDF not available for fallback text extraction, install: pip install PyMuPDF")
    except Exception as e:
        print(f"[pdf] PyMuPDF text extraction failed: {e}")

    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTTextContainer

        pages = []
        for i, layout in enumerate(extract_pages(pdf_path), 1):
            chunks = []
            for element in layout:
                if isinstance(element, LTTextContainer):
                    text = element.get_text()
                    if text and text.strip():
                        chunks.append(text.strip())
            page_text = "\n".join(chunks).strip()
            if page_text:
                pages.append(f"--- Page {i} ---\n{page_text}")
        if pages:
            return pages
    except ImportError:
        print("[pdf] pdfminer.six not available for fallback text extraction, install: pip install pdfminer.six")
    except Exception as e:
        print(f"[pdf] pdfminer text extraction failed: {e}")

    return []


def extract_pdf_images(pdf_path, image_dir, base_name):
    """Extract images from PDF using pdf2image (renders pages as images).
    For embedded image extraction, use PyMuPDF (fitz) if available.
    """
    image_count = 0

    # Try PyMuPDF first (better embedded image extraction)
    try:
        import fitz
        doc = fitz.open(pdf_path)
        for i, page in enumerate(doc, 1):
            images = page.get_images()
            for j, img in enumerate(images):
                xref = img[0]
                base_image = doc.extract_image(xref)
                img_bytes = base_image["image"]
                ext = base_image["ext"]
                img_name = f"{base_name}_page{i}_{j}.{ext}"
                img_path = os.path.join(image_dir, img_name)
                with open(img_path, 'wb') as f:
                    f.write(img_bytes)
                image_count += 1
        doc.close()
        return image_count
    except ImportError:
        pass

    # Fallback: render each page as image using pdf2image
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(pdf_path)
        for i, img in enumerate(images, 1):
            img_name = f"{base_name}_page{i}.png"
            img_path = os.path.join(image_dir, img_name)
            img.save(img_path, 'PNG')
            image_count += 1
        return image_count
    except ImportError:
        print("[pdf] pdf2image not available for page rendering")
        return 0
    except Exception as e:
        print(f"[pdf] page rendering failed: {e}")
        print("[pdf] If you rely on pdf2image, verify that Poppler is installed and on PATH.")
    
    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(pdf_path)
        for i, page in enumerate(doc, 1):
            bitmap = page.render(scale=1.5)
            pil_image = bitmap.to_pil()
            img_name = f"{base_name}_page{i}.png"
            img_path = os.path.join(image_dir, img_name)
            pil_image.save(img_path, "PNG")
            image_count += 1
        doc.close()
        return image_count
    except ImportError:
        print("[pdf] pypdfium2 not available for page rendering")
        return 0
    except Exception as e:
        print(f"[pdf] pypdfium2 page rendering failed: {e}")
        return 0


def main():
    if len(sys.argv) < 4:
        print("Usage: python extract_pdf.py <pdf_file_or_dir> <text_dir> <image_dir>")
        sys.exit(1)

    pdf_source = sys.argv[1]
    text_dir = sys.argv[2]
    image_dir = sys.argv[3]

    os.makedirs(text_dir, exist_ok=True)
    os.makedirs(image_dir, exist_ok=True)

    if os.path.isfile(pdf_source):
        pdf_files = [pdf_source]
    else:
        pdf_files = [
            os.path.join(pdf_source, f)
            for f in sorted(os.listdir(pdf_source))
            if f.endswith('.pdf') and not f.startswith('~')
        ]

    for path in pdf_files:
        f = os.path.basename(path)
        if f.endswith('.pdf') and not f.startswith('~'):
            base_name = os.path.splitext(f)[0]

            # Extract text
            pages = extract_pdf_text(path)
            if pages:
                joined = '\n\n'.join(pages)
                joined = ''.join(ch if ord(ch) < 0xD800 or ord(ch) > 0xDFFF else '\ufffd' for ch in joined)
                text_out = os.path.join(text_dir, f"{base_name}.txt")
                with open(text_out, 'w', encoding='utf-8') as wf:
                    wf.write(joined)
            else:
                print("[pdf] no extractable text; use OCR/page ranges or page images before semantic outline generation")

            # Extract images
            img_count = extract_pdf_images(path, image_dir, base_name)
            print(f"[pdf] {f}: {len(pages)} pages text, {img_count} images")


if __name__ == '__main__':
    main()


