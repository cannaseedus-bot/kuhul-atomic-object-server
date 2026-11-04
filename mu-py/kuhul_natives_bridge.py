# ⟁ K'UHUL NATIVES BRIDGE - Python Native Operations ⟁
# Provides grep, glob, shell, text, system-info operations via CLI

import sys
import os
import json
import subprocess
import time
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict

# ============================================================================
# CLI ARGUMENT PARSING
# ============================================================================

def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description='K\'UHUL Natives Bridge')
    
    # Operations
    parser.add_argument('--grep', action='store_true', help='Execute grep search')
    parser.add_argument('--glob', action='store_true', help='Execute glob matching')
    parser.add_argument('--shell', action='store_true', help='Execute shell command')
    parser.add_argument('--system-info', action='store_true', help='Get system info')
    
    # Grep options
    parser.add_argument('--pattern', type=str, help='Search pattern')
    parser.add_argument('--path', type=str, default='.', help='Search path')
    parser.add_argument('--ignore-case', action='store_true', help='Case insensitive')
    parser.add_argument('--recursive', action='store_true', help='Recursive search')
    parser.add_argument('--include', type=str, help='File pattern to include')
    
    # Glob options
    parser.add_argument('--hidden', action='store_true', help='Include hidden files')
    
    # Shell options
    parser.add_argument('--command', type=str, help='Shell command')
    parser.add_argument('--cwd', type=str, help='Working directory')
    parser.add_argument('--timeout', type=int, help='Timeout in seconds')
    
    return parser.parse_args()

# ============================================================================
# GREP IMPLEMENTATION
# ============================================================================

def execute_grep(args) -> Dict[str, Any]:
    """Execute grep search"""
    pattern = args.pattern
    path = args.path
    ignore_case = args.ignore_case
    recursive = args.recursive
    include = args.include
    
    matches = []
    files_searched = 0
    
    # Build grep command
    cmd = ['grep']
    if ignore_case:
        cmd.append('-i')
    if recursive:
        cmd.append('-r')
    if include:
        cmd.extend(['--include', include])
    cmd.extend(['-n', pattern, path])
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if ':' in line:
                    parts = line.split(':', 2)
                    if len(parts) >= 3:
                        file_path, line_num, content = parts
                        matches.append({
                            'file': file_path,
                            'line': int(line_num),
                            'content': content.rstrip()
                        })
                        files_searched += 1
    except Exception as e:
        print(json.dumps({'error': str(e)}))
        return {'matches': [], 'total_matches': 0, 'files_searched': 0}
    
    return {
        'matches': matches,
        'total_matches': len(matches),
        'files_searched': files_searched
    }

# ============================================================================
# GLOB IMPLEMENTATION
# ============================================================================

def execute_glob(args) -> Dict[str, Any]:
    """Execute glob pattern matching"""
    pattern = args.pattern
    path = args.path
    recursive = args.recursive
    include_hidden = args.hidden
    
    files = []
    
    try:
        search_path = Path(path)
        
        if recursive:
            if include_hidden:
                matcher = search_path.rglob(pattern)
            else:
                matcher = search_path.rglob(pattern)
                files = [str(f) for f in matcher if not any(p.startswith('.') for p in f.parts)]
        else:
            matcher = search_path.glob(pattern)
            files = [str(f) for f in matcher]
        
        if not include_hidden:
            files = [f for f in files if not Path(f).name.startswith('.')]
            
    except Exception as e:
        print(json.dumps({'error': str(e)}))
        return {'files': [], 'total_files': 0}
    
    return {
        'files': sorted(files),
        'total_files': len(files)
    }

# ============================================================================
# SHELL IMPLEMENTATION
# ============================================================================

def execute_shell(args) -> Dict[str, Any]:
    """Execute shell command"""
    command = args.command
    cwd = args.cwd
    timeout = args.timeout
    
    start_time = time.time()
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd
        )
        
        duration = time.time() - start_time
        
        return {
            'stdout': result.stdout,
            'stderr': result.stderr,
            'exit_code': result.returncode,
            'killed': False,
            'duration': round(duration, 3)
        }
        
    except subprocess.TimeoutExpired:
        return {
            'stdout': '',
            'stderr': f'Command timed out after {timeout}s',
            'exit_code': -1,
            'killed': True,
            'duration': timeout
        }
    except Exception as e:
        return {
            'stdout': '',
            'stderr': str(e),
            'exit_code': -1,
            'killed': False,
            'duration': 0
        }

# ============================================================================
# SYSTEM INFO IMPLEMENTATION
# ============================================================================

def get_system_info() -> Dict[str, Any]:
    """Get system information"""
    import platform
    import multiprocessing
    
    info = {
        'platform': platform.system(),
        'platform_release': platform.release(),
        'platform_version': platform.version(),
        'arch': platform.machine(),
        'processor': platform.processor(),
        'cpu_count': multiprocessing.cpu_count(),
        'python_version': platform.python_version(),
    }
    
    # Memory info
    try:
        import psutil
        mem = psutil.virtual_memory()
        info['memory_total_mb'] = round(mem.total / (1024 * 1024))
        info['memory_available_mb'] = round(mem.available / (1024 * 1024))
    except ImportError:
        # Fallback without psutil
        if os.name == 'nt':
            import ctypes
            kernel32 = ctypes.windll.kernel32
            c_ulonglong = ctypes.c_ulonglong
            
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ('dwLength', ctypes.c_ulong),
                    ('dwMemoryLoad', ctypes.c_ulong),
                    ('ullTotalPhys', c_ulonglong),
                    ('ullAvailPhys', c_ulonglong),
                    ('ullTotalPageFile', c_ulonglong),
                    ('ullAvailPageFile', c_ulonglong),
                    ('ullTotalVirtual', c_ulonglong),
                    ('ullAvailVirtual', c_ulonglong),
                    ('ullAvailExtendedVirtual', c_ulonglong),
                ]
            
            memStatus = MEMORYSTATUSEX()
            memStatus.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            kernel32.GlobalMemoryStatusEx(ctypes.byref(memStatus))
            
            info['memory_total_mb'] = round(memStatus.ullTotalPhys / (1024 * 1024))
            info['memory_available_mb'] = round(memStatus.ullAvailPhys / (1024 * 1024))
    
    # GPU info (Windows)
    if os.name == 'nt':
        try:
            result = subprocess.run(
                ['powershell', '-Command', 'Get-WmiObject Win32_VideoController | Select-Object -ExpandProperty Name'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                gpus = [g.strip() for g in result.stdout.strip().split('\n') if g.strip()]
                if gpus:
                    info['gpu_name'] = gpus[0]
                    info['gpu_count'] = len(gpus)
        except:
            pass
    
    return info

# ============================================================================
# TEXT UTILITIES
# ============================================================================

def visible_width(text: str) -> int:
    """Calculate visible width of text (ANSI-aware, CJK-aware)"""
    # Strip ANSI codes
    ansi_pattern = r'\x1b\[[0-9;]*[a-zA-Z]'
    stripped = re.sub(ansi_pattern, '', text)
    
    width = 0
    for c in stripped:
        # CJK characters count as double width
        if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f':
            width += 2
        else:
            width += 1
    
    return width

def truncate_to_width(text: str, max_width: int, ellipsis: str = '...') -> str:
    """Truncate text to visible width"""
    if not text or max_width <= 0:
        return text or ''
    
    current_width = visible_width(text)
    if current_width <= max_width:
        return text
    
    ellipsis_width = visible_width(ellipsis)
    available_width = max_width - ellipsis_width
    
    # Simple truncation (production would handle grapheme clusters)
    truncated = text[:available_width] if len(text) > available_width else text
    return truncated + ellipsis

# ============================================================================
# MAIN
# ============================================================================

def main():
    args = parse_args()
    
    result = None
    
    if args.grep:
        result = execute_grep(args)
    elif args.glob:
        result = execute_glob(args)
    elif args.shell:
        result = execute_shell(args)
    elif args.system_info:
        result = get_system_info()
    else:
        print("Usage: kuhul_natives_bridge.py [--grep|--glob|--shell|--system-info] [options]")
        print()
        print("Operations:")
        print("  --grep          Search files for pattern")
        print("  --glob          Match files by pattern")
        print("  --shell         Execute shell command")
        print("  --system-info   Get system information")
        sys.exit(1)
    
    if result is not None:
        print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
