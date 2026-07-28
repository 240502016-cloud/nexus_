$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class NexusIconNative {
  [DllImport("user32.dll", CharSet = CharSet.Auto)]
  public static extern bool DestroyIcon(IntPtr handle);
}
"@

$assetDirectory = Join-Path $PSScriptRoot "..\assets"
$assetDirectory = [IO.Path]::GetFullPath($assetDirectory)
[IO.Directory]::CreateDirectory($assetDirectory) | Out-Null

$bitmap = New-Object Drawing.Bitmap 256, 256
$graphics = [Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.TextRenderingHint = [Drawing.Text.TextRenderingHint]::AntiAliasGridFit

$bounds = New-Object Drawing.Rectangle 0, 0, 256, 256
$gradient = New-Object Drawing.Drawing2D.LinearGradientBrush(
  $bounds,
  [Drawing.Color]::FromArgb(124, 92, 255),
  [Drawing.Color]::FromArgb(82, 57, 207),
  45
)
$path = New-Object Drawing.Drawing2D.GraphicsPath
$radius = 58
$diameter = $radius * 2
$path.AddArc(0, 0, $diameter, $diameter, 180, 90)
$path.AddArc(256 - $diameter, 0, $diameter, $diameter, 270, 90)
$path.AddArc(256 - $diameter, 256 - $diameter, $diameter, $diameter, 0, 90)
$path.AddArc(0, 256 - $diameter, $diameter, $diameter, 90, 90)
$path.CloseFigure()
$graphics.FillPath($gradient, $path)

$glow = New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(42, 255, 255, 255))
$graphics.FillEllipse($glow, 24, -74, 220, 170)

$font = New-Object Drawing.Font("Segoe UI", 126, [Drawing.FontStyle]::Bold, [Drawing.GraphicsUnit]::Pixel)
$textBrush = New-Object Drawing.SolidBrush([Drawing.Color]::White)
$format = New-Object Drawing.StringFormat
$format.Alignment = [Drawing.StringAlignment]::Center
$format.LineAlignment = [Drawing.StringAlignment]::Center
$graphics.DrawString("N", $font, $textBrush, (New-Object Drawing.RectangleF 0, 2, 256, 248), $format)

$pngPath = Join-Path $assetDirectory "icon.png"
$icoPath = Join-Path $assetDirectory "icon.ico"
$bitmap.Save($pngPath, [Drawing.Imaging.ImageFormat]::Png)

$iconHandle = $bitmap.GetHicon()
try {
  $icon = [Drawing.Icon]::FromHandle($iconHandle)
  $stream = [IO.File]::Open($icoPath, [IO.FileMode]::Create)
  try {
    $icon.Save($stream)
  } finally {
    $stream.Dispose()
    $icon.Dispose()
  }
} finally {
  [NexusIconNative]::DestroyIcon($iconHandle) | Out-Null
}

$format.Dispose()
$textBrush.Dispose()
$font.Dispose()
$glow.Dispose()
$path.Dispose()
$gradient.Dispose()
$graphics.Dispose()
$bitmap.Dispose()

Write-Output "Generated $icoPath and $pngPath"
