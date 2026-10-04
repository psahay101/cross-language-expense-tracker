param(
    [string]$OutputFolder = 'C:\cumberlands\residency'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$docsRoot = Join-Path $projectRoot 'docs'
$specification = [System.IO.File]::ReadAllText((Join-Path $docsRoot 'presentation_content.json')) | ConvertFrom-Json
if ($specification.slides.Count -ne 10) { throw 'The deck must contain exactly 10 slides.' }
if (($specification.slides | Measure-Object duration_seconds -Sum).Sum -ne 600) { throw 'The speaking plan must total 10 minutes.' }
[void][System.IO.Directory]::CreateDirectory($OutputFolder)
$previewRoot = Join-Path $docsRoot 'slide_previews'
[void][System.IO.Directory]::CreateDirectory($previewRoot)

function Rgb([int]$Red, [int]$Green, [int]$Blue) { return $Red + 256 * $Green + 65536 * $Blue }
$navy = Rgb 23 43 61
$teal = Rgb 0 120 119
$gray = Rgb 84 103 117
$pale = Rgb 242 246 248
$white = Rgb 255 255 255
$terminal = Rgb 25 35 46
$mint = Rgb 187 238 220
$shapeChecks = New-Object System.Collections.Generic.List[object]

function Add-Text {
    param($Slide, [string]$Text, [double]$X, [double]$Y, [double]$Width, [double]$Height,
          [double]$Size = 24, [int]$Color = $navy, [bool]$Bold = $false,
          [string]$Font = 'Aptos', [int]$Align = 1)
    $shape = $Slide.Shapes.AddTextbox(1, $X, $Y, $Width, $Height)
    $shape.TextFrame.MarginLeft = 0
    $shape.TextFrame.MarginRight = 0
    $shape.TextFrame.MarginTop = 0
    $shape.TextFrame.MarginBottom = 0
    $shape.TextFrame.WordWrap = -1
    $shape.TextFrame.TextRange.Text = $Text
    $shape.TextFrame.TextRange.Font.Name = $Font
    $shape.TextFrame.TextRange.Font.Size = $Size
    $shape.TextFrame.TextRange.Font.Bold = if ($Bold) { -1 } else { 0 }
    $shape.TextFrame.TextRange.Font.Color.RGB = $Color
    $shape.TextFrame.TextRange.ParagraphFormat.Alignment = $Align
    $shape.TextFrame.TextRange.ParagraphFormat.SpaceAfter = 0
    $shape.TextFrame.TextRange.ParagraphFormat.SpaceWithin = 1.15
    $shapeChecks.Add([pscustomobject]@{Slide=$Slide.SlideIndex; Shape=$shape; Text=$Text; BoxHeight=$Height; BoxWidth=$Width})
    return $shape
}

function Add-Panel($Slide, [double]$X, [double]$Y, [double]$Width, [double]$Height, [int]$Color) {
    $shape = $Slide.Shapes.AddShape(1, $X, $Y, $Width, $Height)
    $shape.Fill.ForeColor.RGB = $Color
    $shape.Line.Visible = 0
    return $shape
}

function Add-Points($Slide, $Points, [double]$X, [double]$Y, [double]$Width, [double]$Gap = 70) {
    for ($pointIndex = 0; $pointIndex -lt $Points.Count; $pointIndex++) {
        [void](Add-Panel $Slide $X ($Y + $pointIndex * $Gap + 10) 6 24 $teal)
        [void](Add-Text -Slide $Slide -Text $Points[$pointIndex] -X ($X + 24) -Y ($Y + $pointIndex * $Gap) -Width ($Width - 24) -Height 58 -Size 24)
    }
}

$powerpoint = $null
$presentation = $null
try {
    $powerpoint = New-Object -ComObject PowerPoint.Application
    $presentation = $powerpoint.Presentations.Add(0)
    $presentation.PageSetup.SlideWidth = 960
    $presentation.PageSetup.SlideHeight = 540
    for ($slideIndex = 0; $slideIndex -lt 10; $slideIndex++) {
        $item = $specification.slides[$slideIndex]
        $slide = $presentation.Slides.Add($slideIndex + 1, 12)
        $slide.FollowMasterBackground = 0
        $slide.Background.Fill.Solid()
        $slide.Background.Fill.ForeColor.RGB = $white
        if ($item.layout -eq 'title') {
            $slide.Background.Fill.ForeColor.RGB = $navy
            [void](Add-Panel $slide 52 65 64 7 $mint)
            [void](Add-Text -Slide $slide -Text $item.title -X 52 -Y 104 -Width 850 -Height 83 -Size 54 -Color $white -Bold $true)
            [void](Add-Text -Slide $slide -Text $item.subtitle -X 55 -Y 203 -Width 850 -Height 65 -Size 30 -Color $mint)
            [void](Add-Text -Slide $slide -Text ($specification.authors -join ' and ') -X 55 -Y 300 -Width 850 -Height 44 -Size 25 -Color $white)
            [void](Add-Text -Slide $slide -Text 'MSCS632 | Advanced Programming Languages' -X 55 -Y 351 -Width 850 -Height 40 -Size 20 -Color $white)
            [void](Add-Panel $slide 55 423 166 52 $teal)
            [void](Add-Text -Slide $slide -Text 'Python' -X 70 -Y 435 -Width 136 -Height 34 -Size 23 -Color $white -Bold $true -Align 2)
            [void](Add-Panel $slide 242 423 166 52 $teal)
            [void](Add-Text -Slide $slide -Text 'C++' -X 257 -Y 435 -Width 136 -Height 34 -Size 23 -Color $white -Bold $true -Align 2)
        } else {
            [void](Add-Panel $slide 0 0 960 8 $teal)
            [void](Add-Text -Slide $slide -Text $item.title -X 48 -Y 37 -Width 865 -Height 56 -Size 34 -Bold $true)
            [void](Add-Text -Slide $slide -Text $item.subtitle -X 50 -Y 101 -Width 860 -Height 49 -Size 21 -Color $gray)
            switch ($item.layout) {
                'features' {
                    for ($cardIndex = 0; $cardIndex -lt 4; $cardIndex++) {
                        $card = $item.cards[$cardIndex]
                        $x = 50 + ($cardIndex % 2) * 446
                        $y = 171 + [Math]::Floor($cardIndex / 2) * 158
                        [void](Add-Panel $slide $x $y 413 133 $pale)
                        [void](Add-Text -Slide $slide -Text ('0' + ($cardIndex + 1)) -X ($x + 18) -Y ($y + 17) -Width 52 -Height 34 -Size 22 -Color $teal -Bold $true)
                        [void](Add-Text -Slide $slide -Text $card.title -X ($x + 77) -Y ($y + 16) -Width 310 -Height 43 -Size 25 -Bold $true)
                        [void](Add-Text -Slide $slide -Text $card.body -X ($x + 77) -Y ($y + 63) -Width 310 -Height 60 -Size 20 -Color $gray)
                    }
                }
                'example' {
                    [void](Add-Panel $slide 50 172 354 278 $pale)
                    [void](Add-Text -Slide $slide -Text 'Lunch, campus' -X 75 -Y 198 -Width 300 -Height 48 -Size 27 -Bold $true)
                    [void](Add-Text -Slide $slide -Text '$12.34' -X 75 -Y 256 -Width 300 -Height 81 -Size 49 -Color $teal -Bold $true)
                    [void](Add-Text -Slide $slide -Text "Food`nOctober 2, 2026" -X 75 -Y 355 -Width 300 -Height 77 -Size 23 -Color $gray)
                    for ($stepIndex = 0; $stepIndex -lt 3; $stepIndex++) {
                        [void](Add-Text -Slide $slide -Text (($stepIndex + 1).ToString()) -X 458 -Y (205 + $stepIndex * 87) -Width 42 -Height 41 -Size 28 -Color $teal -Bold $true)
                        [void](Add-Text -Slide $slide -Text $item.steps[$stepIndex] -X 510 -Y (205 + $stepIndex * 87) -Width 393 -Height 62 -Size 25)
                    }
                }
                'storage' {
                    for ($cardIndex = 0; $cardIndex -lt 3; $cardIndex++) {
                        $card = $item.cards[$cardIndex]
                        $x = 50 + $cardIndex * 295
                        [void](Add-Panel $slide $x 177 269 173 $pale)
                        [void](Add-Text -Slide $slide -Text $card.title -X ($x + 17) -Y 202 -Width 235 -Height 63 -Size 25 -Bold $true)
                        [void](Add-Text -Slide $slide -Text $card.body -X ($x + 17) -Y 273 -Width 235 -Height 70 -Size 20 -Color $gray)
                    }
                    [void](Add-Panel $slide 50 378 859 85 $teal)
                    [void](Add-Text -Slide $slide -Text 'Store $12.34 as 1,234 cents to keep totals exact.' -X 73 -Y 401 -Width 813 -Height 46 -Size 26 -Color $white -Bold $true -Align 2)
                }
                'demo' {
                    [void](Add-Panel $slide 50 168 530 292 $terminal)
                    [void](Add-Text -Slide $slide -Text ($item.language + ' output | sample data') -X 73 -Y 187 -Width 483 -Height 32 -Size 17 -Color $mint -Bold $true)
                    [void](Add-Text -Slide $slide -Text $item.output -X 73 -Y 239 -Width 483 -Height 206 -Size 24 -Color $white -Font 'Consolas')
                    Add-Points $slide $item.points 618 210 286 77
                    [void](Add-Text -Slide $slide -Text 'Recorded program output. Live demo commands are in the speaker notes.' -X 52 -Y 473 -Width 845 -Height 25 -Size 13 -Color $gray)
                }
                'code' {
                    for ($codeIndex = 0; $codeIndex -lt 2; $codeIndex++) {
                        $x = 50 + $codeIndex * 443
                        [void](Add-Panel $slide $x 171 416 249 $pale)
                        $label = if ($codeIndex -eq 0) { 'Python' } else { 'C++' }
                        $code = if ($codeIndex -eq 0) { $item.python_code } else { $item.cpp_code }
                        [void](Add-Text -Slide $slide -Text $label -X ($x + 19) -Y 185 -Width 379 -Height 38 -Size 24 -Color $teal -Bold $true)
                        [void](Add-Text -Slide $slide -Text $code -X ($x + 19) -Y 235 -Width 379 -Height 168 -Size 17.5 -Font 'Consolas')
                    }
                    [void](Add-Text -Slide $slide -Text 'Python: hints describe the fields.' -X 55 -Y 435 -Width 399 -Height 56 -Size 20)
                    [void](Add-Text -Slide $slide -Text 'C++: field types are checked during the build.' -X 498 -Y 435 -Width 399 -Height 56 -Size 20)
                }
                'comparison' {
                    $columnX = @(50, 272, 579)
                    $columnWidths = @(222, 307, 331)
                    $headers = @('In our project', 'Python', 'C++')
                    for ($rowIndex = 0; $rowIndex -le 4; $rowIndex++) {
                        $y = 166 + $rowIndex * 62
                        [void](Add-Panel $slide 50 $y 860 60 $(if ($rowIndex -eq 0) { $teal } elseif ($rowIndex % 2 -eq 1) { $pale } else { $white }))
                        for ($columnIndex = 0; $columnIndex -lt 3; $columnIndex++) {
                            $text = if ($rowIndex -eq 0) { $headers[$columnIndex] } else { $item.rows[$rowIndex - 1][$columnIndex] }
                            [void](Add-Text -Slide $slide -Text $text -X ($columnX[$columnIndex] + 11) -Y ($y + 9) -Width ($columnWidths[$columnIndex] - 22) -Height 48 -Size 19 -Color $(if ($rowIndex -eq 0) { $white } else { $navy }) -Bold ($rowIndex -eq 0))
                        }
                    }
                }
                'testing' {
                    [void](Add-Panel $slide 50 183 285 266 $pale)
                    [void](Add-Text -Slide $slide -Text '62' -X 76 -Y 211 -Width 233 -Height 113 -Size 79 -Color $teal -Bold $true -Align 2)
                    [void](Add-Text -Slide $slide -Text 'tests passed' -X 72 -Y 343 -Width 241 -Height 51 -Size 27 -Bold $true -Align 2)
                    Add-Points $slide $item.points 382 205 519 78
                }
                'closing' {
                    Add-Points $slide $item.points 61 185 830 78
                    [void](Add-Text -Slide $slide -Text 'Source code, sample data, tests, and run instructions:' -X 64 -Y 432 -Width 822 -Height 27 -Size 16 -Color $gray)
                    $link = Add-Text -Slide $slide -Text $specification.repository_url -X 64 -Y 466 -Width 825 -Height 30 -Size 16 -Color $teal
                    $link.TextFrame.TextRange.ActionSettings.Item(1).Hyperlink.Address = $specification.repository_url
                }
            }
        }
        $footerColor = if ($item.layout -eq 'title') { $white } else { $gray }
        [void](Add-Text -Slide $slide -Text 'Expense Tracker | Python and C++' -X 50 -Y 514 -Width 650 -Height 19 -Size 10 -Color $footerColor)
        [void](Add-Text -Slide $slide -Text (($slideIndex + 1).ToString() + ' / 10') -X 825 -Y 508 -Width 80 -Height 26 -Size 13 -Color $footerColor -Align 3)
        $notesText = 'Speaker: ' + $item.speaker + '. Time: 1 minute.' + "`r`r" + $item.notes
        if ($item.demo_commands) { $notesText += "`r`rLive demo (from the project folder):`r" + ($item.demo_commands -join "`r") + "`rOn macOS/Linux use python3 and ./build/expense_tracker as needed. Use the slide output if a live demo is unavailable." }
        $notesWritten = $false
        foreach ($placeholder in $slide.NotesPage.Shapes.Placeholders) {
            if ($placeholder.PlaceholderFormat.Type -eq 2) { $placeholder.TextFrame.TextRange.Text = $notesText; $notesWritten = $true; break }
        }
        if (-not $notesWritten) { throw ('Speaker notes could not be added to slide ' + ($slideIndex + 1)) }
    }
    $overflow = @()
    foreach ($check in $shapeChecks) {
        $range = $check.Shape.TextFrame.TextRange
        if ($range.BoundHeight -gt $check.BoxHeight + 1 -or $range.BoundWidth -gt $check.BoxWidth + 2) {
            $overflow += [pscustomobject]@{Slide=$check.Slide;Text=$check.Text;Height=$range.BoundHeight;BoxHeight=$check.BoxHeight;Width=$range.BoundWidth;BoxWidth=$check.BoxWidth}
        }
    }
    if ($overflow.Count) { $overflow | ConvertTo-Json -Depth 4 | Write-Output; throw 'A text box does not fit; adjust the layout before saving.' }
    $pptxPath = Join-Path $docsRoot 'Deliverable 3 - Presentation.pptx'
    $pdfPath = Join-Path $docsRoot 'Deliverable 3 - Presentation.pdf'
    $presentation.SaveAs($pptxPath, 24)
    $presentation.SaveAs($pdfPath, 32)
    foreach ($slideNumber in 1..10) { $presentation.Slides.Item($slideNumber).Export((Join-Path $previewRoot ('slide-' + $slideNumber + '.png')), 'PNG', 1600, 900) }
    $presentation.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($presentation)
    $presentation = $null
    $checkPresentation = $powerpoint.Presentations.Open($pptxPath, -1, 0, 0)
    try { if ($checkPresentation.Slides.Count -ne 10) { throw 'The saved presentation does not contain 10 slides.' } } finally { $checkPresentation.Close(); [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($checkPresentation) }
    Copy-Item -LiteralPath $pptxPath -Destination (Join-Path $OutputFolder 'Day 3 - Presentation - 10 Slides.pptx') -Force
    Copy-Item -LiteralPath $pdfPath -Destination (Join-Path $OutputFolder 'Day 3 - Presentation - 10 Slides.pdf') -Force
    $notes = New-Object System.Text.StringBuilder
    [void]$notes.AppendLine($specification.title)
    [void]$notes.AppendLine('10 slides | 10 minutes | 5 minutes per presenter')
    [void]$notes.AppendLine('Prateek: slides 1-5. Venkata: slides 6-10.')
    [void]$notes.AppendLine($specification.repository_url)
    for ($slideIndex = 0; $slideIndex -lt 10; $slideIndex++) {
        $item = $specification.slides[$slideIndex]
        [void]$notes.AppendLine()
        [void]$notes.AppendLine('Slide ' + ($slideIndex + 1) + ': ' + $item.title + ' | ' + $slideIndex + ':00-' + ($slideIndex + 1) + ':00')
        [void]$notes.AppendLine('Speaker: ' + $item.speaker)
        [void]$notes.AppendLine($item.notes)
        if ($item.demo_commands) { [void]$notes.AppendLine('Live demo commands (from project folder):'); foreach ($command in $item.demo_commands) { [void]$notes.AppendLine($command) } }
    }
    [System.IO.File]::WriteAllText((Join-Path $docsRoot 'presentation_notes.txt'), $notes.ToString(), [System.Text.UTF8Encoding]::new($false))
    [System.IO.File]::WriteAllText((Join-Path $OutputFolder 'Day 3 - Presentation - Speaker Notes.txt'), $notes.ToString(), [System.Text.UTF8Encoding]::new($false))
    Write-Output 'Verified: 10 slides, speaker notes on every slide, 10-minute plan, no overflowing text.'
    Write-Output ('PowerPoint: ' + (Join-Path $OutputFolder 'Day 3 - Presentation - 10 Slides.pptx'))
    Write-Output ('PDF: ' + (Join-Path $OutputFolder 'Day 3 - Presentation - 10 Slides.pdf'))
} finally {
    if ($presentation) { try { $presentation.Close() } catch {}; [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($presentation) }
    if ($powerpoint) { try { $powerpoint.Quit() } catch {}; [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($powerpoint) }
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}
