import psutil
import os

def find_actual_cwd():
    """Try to find the actual project directory by inspecting parent processes."""
    try:
        current_process = psutil.Process()
        # Look up the process tree up to 5 levels
        for _ in range(5):
            parent = current_process.parent()
            if not parent:
                break
                
            cwd = parent.cwd()
            name = parent.name().lower()
            
            # If the parent is an IDE or Agent that typically has a meaningful CWD
            # and that CWD is not root or home
            if name in ('cursor', 'code', 'node', 'python', 'bash', 'zsh', 'amp', 'claude'):
                if cwd and cwd not in ('/', os.path.expanduser('~')):
                    return cwd
                    
            current_process = parent
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
        pass
    return None

print(f"Detected CWD: {find_actual_cwd()}")
