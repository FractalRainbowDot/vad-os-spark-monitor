# Rebuild the multi-resolution Windows icon using only System.Drawing.
Add-Type -AssemblyName System.Drawing
$ErrorActionPreference = 'Stop'
$frames = @()
foreach ($size in @(16, 24, 32, 48, 64, 128, 256)) {
    $bitmap = New-Object Drawing.Bitmap($size, $size)
    $g = [Drawing.Graphics]::FromImage($bitmap)
    $g.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.ScaleTransform(($size / 256.0), ($size / 256.0))
    $g.Clear([Drawing.Color]::Transparent)
    $background = New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(255, 17, 20, 26))
    $gold = New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(255, 255, 199, 0))
    $border = New-Object Drawing.Pen([Drawing.Color]::FromArgb(255, 255, 199, 0), 7)
    $g.FillRectangle($background, 12, 12, 232, 232)
    $g.DrawRectangle($border, 16, 16, 224, 224)
    # Bold bolt, legible even at 16px.
    [Drawing.PointF[]]$bolt = @(
        [Drawing.PointF]::new(133, 40),
        [Drawing.PointF]::new(74, 140),
        [Drawing.PointF]::new(119, 140),
        [Drawing.PointF]::new(101, 205),
        [Drawing.PointF]::new(184, 109),
        [Drawing.PointF]::new(139, 109),
        [Drawing.PointF]::new(166, 40)
    )
    $g.FillPolygon($gold, $bolt)
    $stream = New-Object IO.MemoryStream
    $bitmap.Save($stream, [Drawing.Imaging.ImageFormat]::Png)
    $frames += ,($stream.ToArray())
    if ($size -eq 256) {
        $bitmap.Save((Join-Path $PSScriptRoot 'spark-monitor.png'), [Drawing.Imaging.ImageFormat]::Png)
    }
    $stream.Dispose()
    $border.Dispose()
    $background.Dispose()
    $gold.Dispose()
    $g.Dispose()
    $bitmap.Dispose()
}
$file = [IO.File]::Create((Join-Path $PSScriptRoot 'spark-monitor.ico'))
$writer = New-Object IO.BinaryWriter($file)
try {
    $writer.Write([uint16]0)
    $writer.Write([uint16]1)
    $writer.Write([uint16]$frames.Count)
    $offset = 6 + 16 * $frames.Count
    $sizes = @(16, 24, 32, 48, 64, 128, 256)
    for ($i = 0; $i -lt $frames.Count; $i++) {
        $dimension = if ($sizes[$i] -eq 256) { 0 } else { $sizes[$i] }
        $writer.Write([byte]$dimension)
        $writer.Write([byte]$dimension)
        $writer.Write([byte]0)
        $writer.Write([byte]0)
        $writer.Write([uint16]1)
        $writer.Write([uint16]32)
        $writer.Write([uint32]$frames[$i].Length)
        $writer.Write([uint32]$offset)
        $offset += $frames[$i].Length
    }
    foreach ($frame in $frames) { $writer.Write([byte[]]$frame) }
} finally {
    $writer.Dispose()
}
