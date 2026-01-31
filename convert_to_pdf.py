#!/usr/bin/env python3
"""
Script to convert QUICKSALES_FEATURES.md to PDF
"""
import markdown
from xhtml2pdf import pisa
import os

def convert_md_to_html(md_file):
    """Convert markdown to HTML"""
    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    # Convert markdown to HTML
    html_content = markdown.markdown(md_content, extensions=['extra', 'tables'])
    
    # Add CSS styling
    styled_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            @page {{
                size: A4;
                margin: 2cm;
            }}
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 100%;
            }}
            h1 {{
                color: #2c3e50;
                border-bottom: 3px solid #3498db;
                padding-bottom: 10px;
                margin-top: 30px;
                font-size: 28px;
            }}
            h2 {{
                color: #34495e;
                border-bottom: 2px solid #95a5a6;
                padding-bottom: 8px;
                margin-top: 25px;
                font-size: 24px;
            }}
            h3 {{
                color: #7f8c8d;
                margin-top: 20px;
                font-size: 20px;
            }}
            h4 {{
                color: #95a5a6;
                margin-top: 15px;
                font-size: 16px;
            }}
            ul, ol {{
                margin-left: 20px;
            }}
            li {{
                margin-bottom: 8px;
            }}
            code {{
                background-color: #f4f4f4;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Courier New', monospace;
            }}
            pre {{
                background-color: #f4f4f4;
                padding: 15px;
                border-radius: 5px;
                overflow-x: auto;
            }}
            hr {{
                border: none;
                border-top: 2px solid #ecf0f1;
                margin: 30px 0;
            }}
            strong {{
                color: #2c3e50;
            }}
            .header {{
                text-align: center;
                margin-bottom: 40px;
            }}
            .header h1 {{
                color: #3498db;
                font-size: 36px;
                border: none;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>QUICKSALES</h1>
            <p><strong>Complete Feature Documentation</strong></p>
        </div>
        {html_content}
    </body>
    </html>
    """
    
    return styled_html

def convert_html_to_pdf(html_content, output_pdf):
    """Convert HTML to PDF"""
    with open(output_pdf, "wb") as pdf_file:
        # Convert HTML to PDF
        pisa_status = pisa.CreatePDF(html_content, dest=pdf_file)
    
    return pisa_status.err

if __name__ == '__main__':
    md_file = 'QUICKSALES_FEATURES.md'
    pdf_file = 'QUICKSALES_FEATURES.pdf'
    
    print(f"Converting {md_file} to PDF...")
    
    # Convert markdown to HTML
    html_content = convert_md_to_html(md_file)
    
    # Convert HTML to PDF
    error = convert_html_to_pdf(html_content, pdf_file)
    
    if not error:
        print(f"✓ Successfully created {pdf_file}")
        print(f"✓ File size: {os.path.getsize(pdf_file) / 1024:.2f} KB")
    else:
        print(f"✗ Error creating PDF")
