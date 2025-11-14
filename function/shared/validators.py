"""Validation and sanitization functions for webhook inputs."""

import logging
import os
import imghdr

# Define maximum file size (10MB for screenshots)
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB in bytes

# Define maximum request size (10MB)
MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10MB in bytes


def validate_file_upload(file_obj, req):
    """
    Validate uploaded file size.
    
    Args:
        file_obj: File object from request
        req: HTTP request object for header access
        
    Returns:
        tuple: (is_valid, error_message)
    """
    # Check content length from headers first
    content_length = req.headers.get('Content-Length')
    if content_length and int(content_length) > MAX_FILE_SIZE:
        return False, f"File too large. Maximum size is {MAX_FILE_SIZE / (1024*1024):.0f}MB"
    
    # Read file with size limit
    file_obj.stream.seek(0, 2)  # Seek to end
    file_size = file_obj.stream.tell()
    file_obj.stream.seek(0)  # Reset to beginning
    
    if file_size > MAX_FILE_SIZE:
        return False, f"File too large. Maximum size is {MAX_FILE_SIZE / (1024*1024):.0f}MB"
    
    if file_size == 0:
        return False, "File is empty"
    
    return True, None


def validate_image_file(file_obj, filename):
    """
    Validate that uploaded file is actually an image.
    
    Args:
        file_obj: File object to validate
        filename: Original filename
        
    Returns:
        tuple: (is_valid, error_message, detected_type)
    """
    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic'}
    
    # Check file extension
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}", None
    
    # Read first bytes to detect actual file type
    file_obj.stream.seek(0)
    header = file_obj.stream.read(512)
    file_obj.stream.seek(0)
    
    # Detect image type from magic bytes
    detected_type = imghdr.what(None, h=header)
    
    if detected_type not in ['jpeg', 'png']:
        return False, "File content does not match image format", detected_type
    
    return True, None, detected_type


def sanitize_text_input(text, field_name, max_length=1000):
    """
    Sanitize and validate text input.
    
    Args:
        text: Input text to sanitize
        field_name: Name of the field (for logging)
        max_length: Maximum allowed length
        
    Returns:
        Sanitized text or None
    """
    if not text:
        return None
    
    # Convert to string and strip whitespace
    text = str(text).strip()
    
    # Check length
    if len(text) > max_length:
        logging.warning(f"{field_name} exceeded max length ({len(text)} > {max_length})")
        text = text[:max_length]
    
    # Remove null bytes and other control characters
    text = ''.join(char for char in text if char.isprintable() or char.isspace())
    
    return text if text else None
