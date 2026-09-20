param([string]$ImagePath = '', [string]$ProcessName = 'obs64', [double]$CropTop = 0.55, [double]$CropHeight = 0.43)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Runtime.WindowsRuntime
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class GameWindow {
 [StructLayout(LayoutKind.Sequential)] public struct Rect { public int L,T,R,B; }
 [StructLayout(LayoutKind.Sequential)] public struct Point { public int X,Y; }
 [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h,out Rect r);
 [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h,ref Point p);
 [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(Point p);
 [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h,uint flags);
 public delegate bool EnumProc(IntPtr h, IntPtr l);
 [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h,System.Text.StringBuilder s,int max);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
 public static IntPtr Projector(int pid) {
  IntPtr result=IntPtr.Zero;
  EnumWindows((h,l)=>{uint owner;GetWindowThreadProcessId(h,out owner);
   if(owner==pid && IsWindowVisible(h) && !IsIconic(h)) {
    var title=new System.Text.StringBuilder(512);GetWindowText(h,title,512);
    if(title.ToString().IndexOf("Projector",StringComparison.OrdinalIgnoreCase)>=0 || title.ToString().Contains("投影")) {result=h;return false;}
   }return true;
  },IntPtr.Zero);return result;
 }
 public static bool RegionVisible(IntPtr h,int x,int y,int w,int height) {
  // Window hit-testing can assign the exact monitor seam to a neighbour.
  // Sample inside the client area, avoiding the non-content window border.
  for(int dy=8;dy<height-8;dy+=8)
   for(int dx=8;dx<w-8;dx+=8) {
    Point p=new Point();p.X=x+dx;p.Y=y+dy;
    if(GetAncestor(WindowFromPoint(p),2)!=h)return false;
   }
  return true;
 }
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr value);
 [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr value);
}
'@
# Use physical pixels across monitors with different display scaling.
[void][GameWindow]::SetProcessDpiAwarenessContext([IntPtr](-4))
[void][GameWindow]::SetThreadDpiAwarenessContext([IntPtr](-4))
$null = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language,Windows.Foundation,ContentType=WindowsRuntime]
$asyncMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
function Await($operation, $type) {
 $task = $asyncMethod.MakeGenericMethod($type).Invoke($null,@($operation))
 $task.Wait()
 return $task.Result
}
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('ja'))
if (!$engine) { throw 'Windows Japanese OCR is not installed.' }
$tempPath = Join-Path $env:TEMP ('jp-journal-' + $PID + '.png')
try {
 do {
  try {
   if ($ImagePath) {
    $source=[System.Drawing.Bitmap]::FromFile($ImagePath)
    try {
     $region=[System.Drawing.Rectangle]::new(0,[int]($source.Height*$CropTop),$source.Width,[int]($source.Height*$CropHeight))
     $cropped=$source.Clone($region,$source.PixelFormat)
     try { $cropped.Save($tempPath,[System.Drawing.Imaging.ImageFormat]::Png) } finally { $cropped.Dispose() }
    } finally { $source.Dispose() }
    $capturePath=$tempPath
   }
   else {
    $obsProcess = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue | Select-Object -First 1
    $game = $null
    if ($obsProcess) { $game = [pscustomobject]@{MainWindowHandle=[GameWindow]::Projector($obsProcess.Id)} }
    if (!$game -or !$game.MainWindowHandle -or [GameWindow]::IsIconic($game.MainWindowHandle)) {
     @{status='Open an OBS windowed Projector (Preview or Source)';text=''} | ConvertTo-Json -Compress
     Start-Sleep -Milliseconds 1200
     continue
    }
    # Read visible pixels without asking the game to redraw via PrintWindow.
    $rect = New-Object GameWindow+Rect
    $point = New-Object GameWindow+Point
    [void][GameWindow]::GetClientRect($game.MainWindowHandle,[ref]$rect)
    [void][GameWindow]::ClientToScreen($game.MainWindowHandle,[ref]$point)
    $w=$rect.R; $h=$rect.B
    if ($w -lt 100 -or $h -lt 100) { Start-Sleep -Milliseconds 1000; continue }
    $cropY=[int]($h*$CropTop); $cropH=[int]($h*$CropHeight)
    if (![GameWindow]::RegionVisible($game.MainWindowHandle,$point.X,($point.Y+$cropY),$w,$cropH)) {
     @{status='Capture waiting: uncover the OBS Projector dialogue area';text=''} | ConvertTo-Json -Compress
     Start-Sleep -Milliseconds 850
     continue
    }
    $bmp = New-Object System.Drawing.Bitmap($w,$cropH)
    $graphics = [System.Drawing.Graphics]::FromImage($bmp)
    try {$graphics.CopyFromScreen($point.X,($point.Y+$cropY),0,0,$bmp.Size);$bmp.Save($tempPath,[System.Drawing.Imaging.ImageFormat]::Png)}
    finally {$graphics.Dispose();$bmp.Dispose()}
    if (![GameWindow]::RegionVisible($game.MainWindowHandle,$point.X,($point.Y+$cropY),$w,$cropH)) {
     Remove-Item -LiteralPath $tempPath -ErrorAction SilentlyContinue
     continue
    }
    $capturePath=$tempPath
   }
   # Keep subtitle glyphs at a reliable recognition size on high-resolution displays.
   $original=[System.Drawing.Bitmap]::FromFile($capturePath)
   try {
    if ($original.Width -gt 1920) {
     $scaled=[System.Drawing.Bitmap]::new($original,1920,[int]($original.Height*1920/$original.Width))
    } else { $scaled=$null }
   } finally { $original.Dispose() }
   if ($scaled) {
    try { $scaled.Save($capturePath,[System.Drawing.Imaging.ImageFormat]::Png) } finally { $scaled.Dispose() }
   }
   $file=Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($capturePath)) ([Windows.Storage.StorageFile])
   $stream=Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
   try {
    $decoder=Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap=Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    try {
     $result=Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
     if ($CropTop -eq 0 -and $CropHeight -eq 1) {
      # Full screens mix HUD numbers, tutorial text and controls at different sizes.
      # Preserve OCR text blocks: global size filtering loses small instructions,
      # and grouping the entire screen by baseline merges HUD into tutorial text.
      $ordered=@($result.Lines | ForEach-Object { $_.Text })
     } else {
     # OCR may split highlighted tips into separate lines. Reassemble words by baseline.
     $words=@($result.Lines | ForEach-Object { $_.Words } | Sort-Object { $_.BoundingRect.Height } -Descending)
     # Small ruby readings above dialogue must not become extra sentence text.
     if ($words.Count -gt 0) {
      $maxHeight=($words | ForEach-Object {$_.BoundingRect.Height} | Measure-Object -Maximum).Maximum
      # Filter complete baselines below, preserving small letters within dialogue.
     }
     $bands=[System.Collections.Generic.List[object]]::new()
     foreach ($word in $words) {
      $center=$word.BoundingRect.Y+$word.BoundingRect.Height
      $band=$bands | Where-Object { [Math]::Abs($_.Center-$center) -lt [Math]::Max(6,$word.BoundingRect.Height*0.5) } | Select-Object -First 1
      if (!$band) {
       $band=[pscustomobject]@{Center=$center;Words=[System.Collections.Generic.List[object]]::new()}
       $bands.Add($band)
      }
      $band.Words.Add($word)
     }
     $ordered=@($bands | Where-Object { ($_.Words | ForEach-Object {$_.BoundingRect.Height} | Measure-Object -Maximum).Maximum -ge $maxHeight*0.55 } | Sort-Object Center | ForEach-Object { ($_.Words | Sort-Object {$_.BoundingRect.X} | ForEach-Object {$_.Text}) -join ' ' })
     }
     @{status='Reading dialogue';text=($ordered -join "`n")} | ConvertTo-Json -Compress
    } finally { $bitmap.Dispose() }
   } finally { $stream.Dispose() }
   } catch { @{status=('Capture error: '+$_.Exception.Message);text=''} | ConvertTo-Json -Compress }
   finally { if (Test-Path -LiteralPath $tempPath) { Remove-Item -LiteralPath $tempPath -ErrorAction SilentlyContinue } }
  if (!$ImagePath) { Start-Sleep -Milliseconds 850 }
 } while (!$ImagePath)
} finally { if (Test-Path -LiteralPath $tempPath) { Remove-Item -LiteralPath $tempPath } }
