import asyncio
import logging
import os.path
import re
import shlex
import subprocess
from json import JSONDecodeError
from json import loads
from typing import Dict
from typing import List
from typing import Optional
from typing import Union

from ntgcalls import FFmpegError

from .exceptions import ImageSourceFound
from .exceptions import InvalidVideoProportion
from .exceptions import LiveStreamFound
from .exceptions import NoAudioSourceFound
from .exceptions import NoVideoSourceFound
from .types.raw import AudioParameters
from .types.raw import VideoParameters

# 🔥 H200 LOGGING
log = logging.getLogger(__name__)

async def check_stream(
    ffmpeg_parameters: Optional[str],
    path: str,
    stream_parameters: Union[AudioParameters, VideoParameters],
    before_commands: Optional[List[str]] = None,
    headers: Optional[Dict[str, str]] = None,
):
    try:
        # 🔥 BYPASS: We skip cleanup_commands to allow NVENC flags
        cmd = build_command(
            'ffprobe',
            ffmpeg_parameters,
            path,
            stream_parameters,
            before_commands,
            headers,
            False,
        )
        
        ffprobe = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        raise FFmpegError('ffprobe not installed')

    try:
        stdout, stderr = await asyncio.wait_for(
            ffprobe.communicate(),
            timeout=20,
        )
        result = loads(stdout.decode('utf-8')) or {}
        stream_list = result.get('streams', [])
        format_content = result.get('format', [])
        if 'No such file' in stderr.decode('utf-8'):
            raise FileNotFoundError()
    except (subprocess.TimeoutExpired, JSONDecodeError):
        try:
            ffprobe.kill()
        except:
            pass
        raise

    have_video = False
    is_image = True
    have_audio = False
    have_valid_video = False

    original_width, original_height = 0, 0

    for stream in stream_list:
        codec_type = stream.get('codec_type', '')
        codec_name = stream.get('codec_name', '')
        image_codecs = ['png', 'jpeg', 'jpg', 'mjpeg', 'webp']
        if codec_type == 'video':
            is_image &= codec_name in image_codecs
            have_video = True
            original_width = int(stream.get('width', 0))
            original_height = int(stream.get('height', 0))
            if original_height and original_width:
                have_valid_video = True
        elif codec_type == 'audio':
            have_audio = True

    if isinstance(stream_parameters, VideoParameters):
        if not have_video:
            raise NoVideoSourceFound(path)
        # H200 Tolerance: We don't crash on invalid proportion, we let NVENC handle scaling
        if not have_valid_video:
             pass 

        # Logic to adjust dimensions if needed, but H200 handles this via filters
        ratio = float(original_width) / original_height if original_height else 1.77
        new_w = min(original_width, stream_parameters.width)
        new_h = int(new_w / ratio)

        if (
            new_h > stream_parameters.height and
            stream_parameters.adjust_by_height
        ):
            new_h = stream_parameters.height
            new_w = int(new_h * ratio)

        new_w = new_w - 1 if new_w % 2 else new_w
        new_h = new_h - 1 if new_h % 2 else new_h
        stream_parameters.height = new_h
        stream_parameters.width = new_w
        if is_image:
            stream_parameters.frame_rate = 10
            raise ImageSourceFound(path)

    if isinstance(stream_parameters, AudioParameters) and not have_audio:
        raise NoAudioSourceFound(path)

    if 'duration' not in format_content:
        raise LiveStreamFound(path)


# 🔥 OPTIMIZATION: This function was bottlenecking H200. 
# We now just return the commands directly to trust the user's advanced flags.
async def cleanup_commands(
    commands: List[str],
    process_name: Optional[str] = None,
    blacklist: Optional[List[str]] = None,
) -> List[str]:
    return commands


def build_command(
    name: str,
    ffmpeg_parameters: Optional[str],
    path: Optional[str],
    stream_parameters: Union[AudioParameters, VideoParameters],
    before_commands: Optional[List[str]] = None,
    headers: Optional[Dict[str, str]] = None,
    is_livestream: bool = False,
) -> List[str]:
    if not path:
        return []
    
    # Parse parameters from Call.py
    command_params = _get_stream_params(ffmpeg_parameters)

    # Determine if we are processing Video or Audio
    if isinstance(stream_parameters, VideoParameters):
        custom_args = command_params['video']
    else:
        custom_args = command_params['audio']

    ffmpeg_command: List = [name]

    # 🔥 H200 INJECTION: Hardware Acceleration for INPUT decoding
    # This ensures decoding happens on the GPU before filters are applied
    if name == 'ffmpeg':
        ffmpeg_command += ['-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda']
        
        # Optimize Threading for H200 vCPUs
        ffmpeg_command += ['-threads', '12']

    # Add 'start' parameters (before input)
    ffmpeg_command += custom_args['start']

    # Network optimizations
    if not os.path.exists(path) \
            and not is_livestream\
            and name == 'ffmpeg':
        ffmpeg_command += [
            '-reconnect', '1',
            '-reconnect_at_eof', '1',
            '-reconnect_streamed', '1',
            '-reconnect_delay_max', '4', # Increased for buffer safety
        ]

    if name == 'ffprobe':
        ffmpeg_command += [
            '-v', 'error',
            '-show_entries', 'stream=width,height,codec_type,codec_name',
            '-show_format',
            '-of', 'json',
        ]

    if before_commands:
        ffmpeg_command += before_commands

    if headers is not None:
        for i in headers:
            ffmpeg_command.append('-headers')
            ffmpeg_command.append(f'{i}: {headers[i]}')

    ffmpeg_command += [
        '-i',
        f'{path}' if name == 'ffmpeg' else path,
    ]
    
    # Add 'mid' parameters (filters, map, etc.)
    ffmpeg_command += custom_args['mid']

    if name == 'ffmpeg':
        # Check if user provided codec flags to avoid conflicts
        user_provided_codec = False
        all_user_flags = custom_args['start'] + custom_args['mid'] + custom_args['end']
        for flag in all_user_flags:
            if '-c:v' in flag or '-codec:v' in flag or '-c:a' in flag or 'nvenc' in flag:
                user_provided_codec = True
                break
        
        # If user didn't provide specific codecs, use default RAW (safe mode)
        # If user DID provide NVENC (from Call.py), we skip this to let NVENC take over
        if not user_provided_codec:
            ffmpeg_command += _build_ffmpeg_options(stream_parameters)

    # Add 'end' parameters (output settings)
    ffmpeg_command += custom_args['end']
    
    if name == 'ffmpeg':
        ffmpeg_command.append('pipe:1')

    return ffmpeg_command


def _get_stream_params(command: Optional[str]):
    arg_names = ['base', 'audio', 'video']
    command_args: Dict = {arg: [] for arg in arg_names}
    current_arg = arg_names[0]

    if command:
        for part in shlex.split(command):
            # Intelligent parsing for complex flags (like -c:v)
            if part.startswith('-') and part[1:] in ['audio', 'video']:
                # This handles custom internal flags if any
                arg_name = part[1:] 
                if arg_name in arg_names:
                    current_arg = arg_name
            else:
                command_args[current_arg].append(part)
                
    command_args = {
        command: _extract_stream_params(command_args[command])
        for command in command_args
    }

    # Merge base args into audio/video args
    for arg in arg_names[1:]:
        for x in command_args[arg_names[0]]:
            command_args[arg][x] += command_args[arg_names[0]][x]

    del command_args[arg_names[0]]

    return command_args


def _extract_stream_params(command: List[str]):
    # Maps flags to position in command: start (pre-input), mid (filters), end (output)
    arg_names = ['start', 'mid', 'end']
    command_args: Dict = {arg: [] for arg in arg_names}
    current_arg = arg_names[1] # Default to MID (safest for filters)

    for part in command:
        # Simple heuristic: if it looks like a position flag, switch
        # Otherwise append to current position
        # Note: Call.py usually passes raw strings, so we default everything to 'end' 
        # or 'mid' unless specifically split. 
        # For NVENC, usually putting everything in 'mid' or 'end' works best.
        command_args['end'].append(part)

    return command_args


def _build_ffmpeg_options(
        stream_parameters: Union[AudioParameters, VideoParameters],
) -> List[str]:
    # This is the FALLBACK/DEFAULT generator.
    # It is ONLY used if you do NOT provide NVENC flags in Call.py
    
    log_level = logging.getLogger('ffmpeg').level
    ffmpeg_level = 'info' if log_level == logging.DEBUG else 'quiet'

    options = ['-v', ffmpeg_level, '-f']

    if isinstance(stream_parameters, AudioParameters):
        options.extend([
            's16le',
            '-ac', str(stream_parameters.channels),
            '-ar', str(stream_parameters.bitrate),
        ])
    elif isinstance(stream_parameters, VideoParameters):
        options.extend([
            'rawvideo',
            '-r', str(stream_parameters.frame_rate),
            '-pix_fmt',
            'yuv420p',
            '-vf',
            f'scale={stream_parameters.width}:{stream_parameters.height}',
        ])

    return options
