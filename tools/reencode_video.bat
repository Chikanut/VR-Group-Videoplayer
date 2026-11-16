@echo off
rem Re-encode a 360 video for the Quest player: HEVC, 4096x4096 by default.
rem   reencode_video.bat "First Battle short (8 min).mp4"            -> "... 4K.mp4" next to it
rem   reencode_video.bat "video.mp4" 4096:2048                       -> lighter, softer vertically
rem Why 4096x4096: the player caps its texture at 4096 px per side, so an 8K (7680x3840) file is
rem shown as 4096x3840 anyway. This keeps that picture and decodes ~43%% fewer pixels.
rem Uses the NVIDIA encoder (fast). No NVIDIA GPU: replace "hevc_nvenc ... -b:v 0" with
rem "libx265 -preset medium -crf 21" (much slower).
setlocal
if "%~1"=="" (
  echo Usage: %~nx0 "input.mp4" [width:height]
  exit /b 1
)
set "SIZE=%~2"
if "%SIZE%"=="" set "SIZE=4096:4096"
ffmpeg -hide_banner -y -i "%~1" ^
  -vf "scale=%SIZE%:flags=lanczos,setsar=1" ^
  -c:v hevc_nvenc -preset p6 -tune hq -rc vbr -cq 23 -b:v 0 -maxrate 40M -bufsize 80M ^
  -profile:v main -pix_fmt yuv420p -g 30 -tag:v hvc1 ^
  -c:a copy -movflags +faststart ^
  "%~dpn1 4K.mp4"
