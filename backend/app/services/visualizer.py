import io
from typing import List, Dict, Any
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from app.core.exceptions import AnalysisException, Stage

class VisualizerService:
    @staticmethod
    def create_masked_document(
        image_bytes: bytes, 
        pii_regions: List[Dict[str, Any]], 
        risk_regions: List[Dict[str, Any]]
    ) -> bytes:
        """
        Draws masks (Black) and Risk Highlights (Red/Yellow) on the image,
        then converts to PDF.
        """
        try:
            from pypdf import PdfReader, PdfWriter
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter


            # Check if input is PDF (by magic bytes or trying to read)
            is_pdf = False
            try:
                reader = PdfReader(io.BytesIO(image_bytes))
                num_pages = len(reader.pages)
                is_pdf = True
            except:
                is_pdf = False

            if not is_pdf:
                # Fallback to Image method
                img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
                w_img, h_img = img.size
                
                # Create a transparent overlay for drawing
                overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)
                
                # Draw PII Masks (Black, solid)
                for pii in pii_regions:
                    if "box_norm" in pii:
                        bn = pii["box_norm"]
                        box = [bn[0]*w_img, bn[1]*h_img, bn[2]*w_img, bn[3]*h_img]
                        draw.rectangle(box, fill=(0, 0, 0, 255))
                    elif "box" in pii:
                        # Legacy fallback
                        draw.rectangle(pii["box"], fill=(0, 0, 0, 255))

                # Draw Risk Highlights
                for risk in risk_regions:
                    box = None
                    if "box_norm" in risk:
                        bn = risk["box_norm"]
                        box = [bn[0]*w_img, bn[1]*h_img, bn[2]*w_img, bn[3]*h_img]
                    elif "box" in risk:
                        box = risk["box"]
                    
                    if box:
                        severity = risk.get("severity", "HIGH")
                        fill_color = (255, 0, 0, 80) if severity == "HIGH" else (255, 165, 0, 80) 
                        outline_color = (255, 0, 0, 255) if severity == "HIGH" else (255, 165, 0, 255)
                        
                        draw.rectangle(box, fill=fill_color, outline=outline_color, width=5)
                        
                        # Badge logic
                        label = risk.get("label", "?")
                        x, y, x2, y2 = box
                        badge_size = 20
                        draw.rectangle([x, y2, x+badge_size, y2+badge_size], fill=outline_color)
                        # Text drawing omitted for simplicity in Image path (requires font load)

                # Composite
                img = Image.alpha_composite(img, overlay)
                img_rgb = img.convert("RGB")
                
                pdf_buffer = io.BytesIO()
                img_rgb.save(pdf_buffer, format="PDF", resolution=100.0)
                return pdf_buffer.getvalue()

            else:
                # PDF Annotation Logic
                writer = PdfWriter()
                
                num_pages = len(reader.pages)
                
                for i in range(num_pages):
                    page = reader.pages[i]
                    
                    # Use CropBox if available, else MediaBox
                    box = page.cropbox
                    page_base_x = float(box.lower_left[0])
                    page_base_y = float(box.lower_left[1])
                    page_width = float(box.width)
                    page_height = float(box.height)
                    
                    # Filter items for this page
                    page_pii = [p for p in pii_regions if p.get("page_idx", 0) == i]
                    page_risk = [r for r in risk_regions if r.get("page_idx", 0) == i]
                    
                    if not page_pii and not page_risk:
                         writer.add_page(page)
                         continue
                    
                    # Create Annotation Layer
                    packet = io.BytesIO()
                    # Canvas size matches cropbox size
                    # Note: We draw relative to (0,0) of this new canvas, 
                    # but we merge it onto the page. Merge usually aligns (0,0) of both.
                    # Since we adding offset manually to coordinates, we might need a canvas matching MediaBox?
                    # Actually, merge_page aligns the lower_left of both?
                    # Safer: Create canvas of page_width/height. Draw assuming (0,0) is lower_left of CropBox.
                    c = canvas.Canvas(packet, pagesize=(page_width, page_height))
                    
                    # NOTE: When merging, logic applies.
                    # If we set page_width/height as canvas size.
                    # We render assuming 0,0 is bottom-left of CROPBOX area.
                    
                    # Draw PII Masks (Black)
                    c.setFillColorRGB(0, 0, 0)
                    for pii in page_pii:
                        if "box_norm" in pii:
                            bn = pii["box_norm"]
                            # Normalized 0..1 relative to CropBox dimensions
                            
                            w = (bn[2] - bn[0]) * page_width
                            h = (bn[3] - bn[1]) * page_height
                            
                            x_in_page = bn[0] * page_width
                            y_top_in_page = bn[1] * page_height 
                            y_bot_in_page = bn[3] * page_height
                            
                            # Convert to PDF Coords (Origin Bottom-Left)
                            # OCR Y=0 is Top. 
                            # PDF Y_Bot = Height - OCR_Y_Bot
                            y_rl = page_height - y_bot_in_page

                            c.rect(x_in_page, y_rl, w, h, fill=1, stroke=0)
                            
                        elif "box" in pii:
                            # Legacy fallback (Absolute coords from OCR assumed to match PDF points?)
                            # Unsafe if OCR uses pixels. Assuming "box_norm" always exists now.
                            pass

                    # Draw Risk Highlights
                    for r_item in page_risk:
                        box_data = None
                        is_norm = False
                        
                        if "box_norm" in r_item:
                            bn = r_item["box_norm"]
                            w = (bn[2] - bn[0]) * page_width
                            h = (bn[3] - bn[1]) * page_height
                            
                            x_in_page = bn[0] * page_width
                            y_bot_in_page = bn[3] * page_height
                            
                            y_rl = page_height - y_bot_in_page
                            
                            # Final drawing coords
                            x = x_in_page
                            y = y_rl
                            is_norm = True
                        else:
                            pass
                                
                        if is_norm:
                            label = r_item.get("label", "!")
                            severity = r_item.get("severity", "HIGH")
                            
                            c.saveState()
                            if severity == "HIGH":
                                c.setStrokeColorRGB(1, 0, 0)
                                c.setFillColorRGB(1, 0, 0)
                            else:
                                c.setStrokeColorRGB(1, 0.85, 0)
                                c.setFillColorRGB(1, 0.85, 0)
                            
                            c.setLineWidth(1)
                            c.setFillAlpha(0.2)
                            c.rect(x, y, w, h, fill=1, stroke=1)
                            c.restoreState()
                            
                            # Draw Number Badge
                            c.setFillColorRGB(1, 0, 0) if severity == "HIGH" else c.setFillColorRGB(1, 0.6, 0)
                            # Badge at top-left of the box
                            # Top-Left Y = y + h
                            c.rect(x, y + h, 14, 14, fill=1, stroke=0) 
                            c.setFillColorRGB(1, 1, 1)
                            c.setFont("Helvetica-Bold", 10)
                            c.drawString(x + 4, y + h + 3, str(label))
                    
                    c.save()
                    
                    # Merge
                    packet.seek(0)
                    new_pdf = PdfReader(packet)
                    # We merge our annotation page (width x height) onto the original page.
                    # Since we sized it to CropBox, but merge_page might align at MediaBox 0,0?
                    # No, usually merge_page overlays 0,0 to 0,0.
                    # If CropBox starts at (100, 100), our drawing at (0,0) will appear at (100,100)?
                    # No, new_pdf 0,0 aligns with base page 0,0. 
                    # If base page CropBox is (100,100), visible area starts there.
                    # We should probably set the MediaBox of our new page to match?
                    # Let's simple try merging:
                    page.merge_page(new_pdf.pages[0])
                    writer.add_page(page)
                
                out_buffer = io.BytesIO()
                writer.write(out_buffer)
                return out_buffer.getvalue()

        except Exception as e:
            # Fallback: Create a simple Error PDF
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            
            err_out = io.BytesIO()
            c = canvas.Canvas(err_out, pagesize=letter)
            c.drawString(100, 700, "Visualization Error:")
            c.drawString(100, 680, str(e))
            c.drawString(100, 660, "Please try uploading a standard PDF or Image.")
            c.save()
            return err_out.getvalue()
