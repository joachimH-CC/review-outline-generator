"""
Windows screenshot fallback.
Captures the full primary screen or a caller-provided region.
Usage: python screenshot.py <output_path> [--region x y w h]
"""
import os
import sys
import subprocess


def screenshot_fullscreen(output_path):
    """Take a full screenshot using PowerShell."""
    ps_script = f'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$screen = [System.Windows.Forms.Screen]::PrimaryScreen
$bmp = New-Object System.Drawing.Bitmap($screen.Bounds.Width, $screen.Bounds.Height)
$gfx = [System.Drawing.Graphics]::FromImage($bmp)
$gfx.CopyFromScreen(0, 0, 0, 0, $screen.Bounds.Size)
$bmp.Save("{output_path}")
$gfx.Dispose()
$bmp.Dispose()
'''
    try:
        subprocess.run(['powershell', '-Command', ps_script],
                       capture_output=True, timeout=30)
        return os.path.exists(output_path)
    except Exception as e:
        print(f"[screenshot] Fullscreen failed: {e}")
        return False


def screenshot_region(output_path, x, y, w, h):
    """Take a screenshot of a specific region."""
    ps_script = f'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap({w}, {h})
$gfx = [System.Drawing.Graphics]::FromImage($bmp)
$gfx.CopyFromScreen({x}, {y}, 0, 0, (New-Object System.Drawing.Size({w}, {h})))
$bmp.Save("{output_path}")
$gfx.Dispose()
$bmp.Dispose()
'''
    try:
        subprocess.run(['powershell', '-Command', ps_script],
                       capture_output=True, timeout=30)
        return os.path.exists(output_path)
    except Exception as e:
        print(f"[screenshot] Region failed: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python screenshot.py <output_path> [--region x y w h]")
        sys.exit(1)

    output_path = sys.argv[1]

    if '--region' in sys.argv and len(sys.argv) >= 7:
        idx = sys.argv.index('--region')
        x, y, w, h = map(int, sys.argv[idx+1:idx+5])
        success = screenshot_region(output_path, x, y, w, h)
    else:
        success = screenshot_fullscreen(output_path)

    if success:
        print(f"[screenshot] Saved to {output_path}")
    else:
        print("[screenshot] Failed")
        sys.exit(1)


if __name__ == '__main__':
    main()
