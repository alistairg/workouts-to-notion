"""
Webhook Capture Script for Apple Shortcuts

This script runs a local webhook listener to capture all data sent from Apple Shortcuts,
including headers, body content, and image attachments. It saves all captured information
to JSON and extracts any images to separate files.

Usage:
    python webhook_capture.py
"""

import json
import base64
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify
import sys

# Configuration
PORT = 8000
HOST = '0.0.0.0'
OUTPUT_DIR = Path(__file__).parent
CAPTURE_FILE = OUTPUT_DIR / f'webhook_capture_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'

app = Flask(__name__)


def save_image(image_data: bytes, content_type: str, field_name: str = 'image') -> dict:
    """
    Save image data to a file and return metadata.
    
    Args:
        image_data: Raw image bytes
        content_type: MIME type of the image
        field_name: Name of the form field or identifier
        
    Returns:
        Dictionary containing image metadata
    """
    # Determine file extension from content type
    extension_map = {
        'image/jpeg': 'jpg',
        'image/jpg': 'jpg',
        'image/png': 'png',
        'image/gif': 'gif',
        'image/heic': 'heic',
        'image/heif': 'heif',
        'image/webp': 'webp',
    }
    
    extension = extension_map.get(content_type.lower(), 'bin')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f'captured_image_{timestamp}.{extension}'
    filepath = OUTPUT_DIR / filename
    
    # Save the image
    with open(filepath, 'wb') as f:
        f.write(image_data)
    
    return {
        'filename': filename,
        'filepath': str(filepath),
        'size_bytes': len(image_data),
        'content_type': content_type,
        'field_name': field_name,
        'saved_at': datetime.now().isoformat()
    }


def capture_webhook_data() -> dict:
    """
    Capture all relevant information from the incoming webhook request.
    
    Returns:
        Dictionary containing all captured data
    """
    captured_data = {
        'timestamp': datetime.now().isoformat(),
        'method': request.method,
        'url': request.url,
        'path': request.path,
        'remote_addr': request.remote_addr,
        'headers': dict(request.headers),
        'args': dict(request.args),
        'form': {},
        'files': [],
        'json_data': None,
        'raw_data': None,
        'content_type': request.content_type,
        'content_length': request.content_length,
    }
    
    # Capture form data
    if request.form:
        captured_data['form'] = dict(request.form)
    
    # Capture files (multipart/form-data)
    if request.files:
        for field_name, file in request.files.items():
            file_data = file.read()
            content_type = file.content_type or 'application/octet-stream'
            
            # Check if it's an image
            if content_type.startswith('image/'):
                image_metadata = save_image(file_data, content_type, field_name)
                captured_data['files'].append(image_metadata)
            else:
                # Save non-image files as well
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f'captured_file_{timestamp}_{file.filename or "unknown"}'
                filepath = OUTPUT_DIR / filename
                
                with open(filepath, 'wb') as f:
                    f.write(file_data)
                
                captured_data['files'].append({
                    'filename': filename,
                    'filepath': str(filepath),
                    'original_filename': file.filename,
                    'size_bytes': len(file_data),
                    'content_type': content_type,
                    'field_name': field_name,
                    'saved_at': datetime.now().isoformat()
                })
    
    # Capture JSON data
    if request.is_json:
        try:
            json_data = request.get_json()
            captured_data['json_data'] = json_data
            
            # Check for base64 encoded images in JSON
            if isinstance(json_data, dict):
                for key, value in json_data.items():
                    if isinstance(value, str) and (
                        key.lower() in ['image', 'photo', 'picture', 'attachment'] or
                        value.startswith('data:image/')
                    ):
                        # Handle data URL format: data:image/jpeg;base64,/9j/4AAQ...
                        if value.startswith('data:'):
                            try:
                                header, encoded = value.split(',', 1)
                                content_type = header.split(';')[0].split(':')[1]
                                image_data = base64.b64decode(encoded)
                                image_metadata = save_image(image_data, content_type, key)
                                captured_data['files'].append(image_metadata)
                            except Exception as e:
                                captured_data.setdefault('warnings', []).append(
                                    f'Failed to decode base64 image from key "{key}": {str(e)}'
                                )
                        # Handle plain base64 string
                        elif len(value) > 100 and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=' for c in value[:100]):
                            try:
                                image_data = base64.b64decode(value)
                                # Try to detect image type from magic bytes
                                content_type = 'image/jpeg'  # Default
                                if image_data[:4] == b'\x89PNG':
                                    content_type = 'image/png'
                                elif image_data[:2] == b'\xff\xd8':
                                    content_type = 'image/jpeg'
                                
                                image_metadata = save_image(image_data, content_type, key)
                                captured_data['files'].append(image_metadata)
                            except Exception as e:
                                captured_data.setdefault('warnings', []).append(
                                    f'Failed to decode base64 from key "{key}": {str(e)}'
                                )
        except Exception as e:
            captured_data['json_parse_error'] = str(e)
    
    # Capture raw data if not JSON or form
    elif request.data:
        raw_data = request.data
        
        # Check if raw data might be an image
        content_type = request.content_type or ''
        if content_type.startswith('image/') or raw_data[:4] in [b'\x89PNG', b'\xff\xd8\xff']:
            # Detect content type from magic bytes if not specified
            if not content_type or content_type == 'application/octet-stream':
                if raw_data[:4] == b'\x89PNG':
                    content_type = 'image/png'
                elif raw_data[:2] == b'\xff\xd8':
                    content_type = 'image/jpeg'
                else:
                    content_type = 'image/unknown'
            
            image_metadata = save_image(raw_data, content_type, 'raw_body')
            captured_data['files'].append(image_metadata)
        else:
            # Try to decode as text
            try:
                captured_data['raw_data'] = raw_data.decode('utf-8')
            except UnicodeDecodeError:
                # Store as base64 if binary
                captured_data['raw_data_base64'] = base64.b64encode(raw_data).decode('utf-8')
                captured_data['raw_data_note'] = 'Binary data, stored as base64'
    
    return captured_data


@app.route('/webhook', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def webhook_handler():
    """
    Main webhook endpoint that captures all data and saves to file.
    """
    print("\n" + "="*60)
    print("📥 Webhook received!")
    print("="*60)
    
    try:
        # Capture all webhook data
        captured_data = capture_webhook_data()
        
        # Save to JSON file
        with open(CAPTURE_FILE, 'w') as f:
            json.dump(captured_data, f, indent=2)
        
        print(f"✅ Data captured and saved to: {CAPTURE_FILE}")
        
        # Print summary
        print("\n📊 Summary:")
        print(f"  Method: {captured_data['method']}")
        print(f"  Content-Type: {captured_data['content_type']}")
        print(f"  Headers: {len(captured_data['headers'])} headers captured")
        print(f"  Files: {len(captured_data['files'])} file(s) captured")
        
        if captured_data['files']:
            print("\n📁 Files saved:")
            for file_info in captured_data['files']:
                print(f"  - {file_info['filename']} ({file_info['size_bytes']} bytes, {file_info['content_type']})")
        
        # Shutdown server after responding
        print("\n🛑 Shutting down server...")
        shutdown_server()
        
        return jsonify({
            'status': 'success',
            'message': 'Webhook data captured successfully',
            'captured_at': captured_data['timestamp'],
            'files_saved': len(captured_data['files'])
        }), 200
        
    except Exception as e:
        error_data = {
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.now().isoformat()
        }
        
        # Save error data
        with open(CAPTURE_FILE, 'w') as f:
            json.dump(error_data, f, indent=2)
        
        print(f"❌ Error: {str(e)}")
        shutdown_server()
        
        return jsonify(error_data), 500


def shutdown_server():
    """
    Gracefully shutdown the Flask server.
    """
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        # For production servers, we'll just exit
        # The response will still be sent before the process exits
        import threading
        def delayed_exit():
            import time
            time.sleep(1)  # Wait 1 second to ensure response is sent
            sys.exit(0)
        
        threading.Thread(target=delayed_exit).start()
    else:
        func()


def get_local_ip():
    """
    Get the local IP address for displaying connection info.
    """
    import socket
    try:
        # Create a socket to determine local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return '127.0.0.1'


if __name__ == '__main__':
    print("\n" + "="*60)
    print("🎯 Webhook Capture Server Starting...")
    print("="*60)
    print(f"\n📝 Output file will be: {CAPTURE_FILE}")
    print(f"📁 Images will be saved to: {OUTPUT_DIR}\n")
    
    local_ip = get_local_ip()
    
    print("🌐 Server Endpoints:")
    print(f"  Local:    http://localhost:{PORT}/webhook")
    print(f"  Network:  http://{local_ip}:{PORT}/webhook")
    print(f"\n💡 Use the network URL in Apple Shortcuts if running on another device")
    print("\n⏳ Waiting for webhook... (Press Ctrl+C to stop)\n")
    print("="*60 + "\n")
    
    try:
        app.run(host=HOST, port=PORT, debug=False)
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped by user")
    except Exception as e:
        print(f"\n\n❌ Server error: {str(e)}")
    finally:
        print("\n👋 Goodbye!\n")
