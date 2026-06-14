import os
import zipfile

def create_zip():
    zip_name = "sentryswarm_code.zip"
    exclude_dirs = {'.git', '.claude', '__pycache__', '.venv', 'venv', 'node_modules'}
    exclude_files = {'presentation.pptx', 'sentryswarm_pitch.pptx', 'make_zip.py', '.env'}
    
    # Walk the directory tree
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk('.'):
            # Skip excluded directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]
            
            for file in files:
                # Skip excluded files
                if file in exclude_files:
                    continue
                file_path = os.path.join(root, file)
                # Skip the output zip file itself
                if os.path.basename(file_path) == zip_name:
                    continue
                # Add file to zip
                zipf.write(file_path, os.path.relpath(file_path, '.'))
                
    print("sentryswarm_code.zip created successfully!")

if __name__ == '__main__':
    create_zip()
