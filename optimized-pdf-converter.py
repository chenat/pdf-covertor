from flask import Flask, request, send_file
import tempfile
import os
import logging
from pdf2image import convert_from_path
from werkzeug.utils import secure_filename
import time
from concurrent.futures import ThreadPoolExecutor
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Thread pool for handling concurrent requests
executor = ThreadPoolExecutor(max_workers=10)

app = Flask(__name__)

# Configuration for performance
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limit upload size to 16MB
ALLOWED_EXTENSIONS = {'pdf'}
PDF_RESOLUTION = 200  # DPI resolution for conversion

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Google Cloud Run."""
    return {'status': 'healthy'}, 200

@app.route('/convert', methods=['POST'])
def convert_pdf_to_jpeg():
    request_id = threading.get_ident()
    start_time = time.time()
    logger.info(f"Request {request_id}: Starting PDF conversion")
    
    # Input validation
    if 'file' not in request.files:
        logger.warning(f"Request {request_id}: No file part in request")
        return {'error': 'No file part'}, 400
    
    pdf_file = request.files['file']
    if pdf_file.filename == '':
        logger.warning(f"Request {request_id}: No file selected")
        return {'error': 'No file selected'}, 400
    
    if not allowed_file(pdf_file.filename):
        logger.warning(f"Request {request_id}: Invalid file type")
        return {'error': 'Only PDF files are allowed'}, 400
    
    try:
        # Create temporary files with auto-cleanup
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as pdf_temp:
            pdf_path = pdf_temp.name
            pdf_file.save(pdf_path)
        
        # Set the page number from query param or default to first page
        page_num = request.args.get('page', default=1, type=int)
        
        # Convert with optimized settings
        logger.info(f"Request {request_id}: Converting PDF to image")
        images = convert_from_path(
            pdf_path,
            dpi=PDF_RESOLUTION,
            first_page=page_num,
            last_page=page_num,
            thread_count=2,  # Use 2 threads for conversion
            use_pdftocairo=True  # Typically faster than poppler
        )
        
        # Check if we have an image
        if not images:
            logger.warning(f"Request {request_id}: No images generated")
            return {'error': 'Failed to convert PDF'}, 500
            
        # Create temporary output file
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as output_temp:
            output_path = output_temp.name
        
        # Get quality parameter from request or use default
        quality = request.args.get('quality', default=85, type=int)
        quality = max(1, min(quality, 95))  # Ensure quality is between 1-95
        
        # Save the image with the specified quality
        images[0].save(output_path, 'JPEG', quality=quality, optimize=True)
        
        # Clean up the input file
        os.unlink(pdf_path)
        
        # Log processing time
        elapsed = time.time() - start_time
        logger.info(f"Request {request_id}: Processing completed in {elapsed:.2f}s")
        
        # Return the file and ensure it's deleted after sending
        response = send_file(output_path, mimetype='image/jpeg')
        response.headers['X-Processing-Time'] = str(elapsed)
        
        # Set cache control for 1 day if the result is cacheable
        response.headers['Cache-Control'] = 'public, max-age=86400'
        
        @response.call_on_close
        def cleanup():
            try:
                os.unlink(output_path)
                logger.debug(f"Request {request_id}: Temporary files cleaned up")
            except Exception as e:
                logger.error(f"Request {request_id}: Error cleaning up: {str(e)}")
        
        return response
        
    except Exception as e:
        logger.error(f"Request {request_id}: Error during conversion: {str(e)}")
        # Clean up in case of errors
        if 'pdf_path' in locals():
            try:
                os.unlink(pdf_path)
            except:
                pass
        if 'output_path' in locals():
            try:
                os.unlink(output_path)
            except:
                pass
        return {'error': f'Conversion failed: {str(e)}'}, 500

if __name__ == '__main__':
    # Get port from environment or use default
    port = int(os.environ.get('PORT', 8080))
    
    # In production, use Gunicorn or similar WSGI server instead of Flask's dev server
    # This code is only for local testing
    app.run(host='0.0.0.0', port=port, threaded=True)
