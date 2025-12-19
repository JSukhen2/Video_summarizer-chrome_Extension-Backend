"""
Video Analysis Backend Server
OpenAI Whisper + Gemini 2.0 Flash 하이브리드 분석 시스템
+ 주요 프레임 추출 기능 (다이어그램, 슬라이드, 중요 장면)
"""

import os
import json
import tempfile
import time
import base64
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
import google.generativeai as genai
from moviepy.editor import VideoFileClip
import tavily
import yt_dlp
from PIL import Image
import io

# 환경 변수 로드
load_dotenv()

app = Flask(__name__)
CORS(app)  # Chrome Extension에서 호출 가능하도록 CORS 허용

# API 키 설정
openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
tavily_client = tavily.TavilyClient(api_key=os.getenv('TAVILY_API_KEY')) if os.getenv('TAVILY_API_KEY') else None

# Gemini 모델 설정
GEMINI_MODEL = 'gemini-2.0-flash-exp'

# 시스템 프롬프트
SYSTEM_PROMPT = """### System Prompt: Video Analysis & Research Expert

**[Role]**
당신은 동영상의 시각적 정보(Gemini)와 음성 스크립트(Whisper)를 통합 분석하는 전문가입니다. 

**[Task 1: Initial Analysis]**
제공된 비디오와 스크립트를 결합하여 다음을 생성하세요:
1. **Detailed Summary**: 영상의 핵심 메시지와 맥락을 설명하는 상세 요약.
2. **Interactive TOC**: [00:00] 형식의 타임스탬프와 함께 주요 장면/주제 전환을 정리한 목차.

**[Task 2: Smart Q&A Logic]**
사용자의 질문에 대해 다음과 같은 우선순위로 답변하세요:
1. **내부 참조**: 질문에 대한 정보가 비디오 내용이나 스크립트에 포함되어 있다면, "영상 내용에 따르면..."으로 시작하여 답변하세요.
2. **외부 확장 (Internet Search)**: 영상에 없는 정보이거나, 최신 정보 확인이 필요한 경우 "영상에는 언급되지 않았으나, 확인 결과..."로 시작하여 인터넷 검색 기반의 정확한 정보를 제공하세요.
3. **거짓 금지**: 확실하지 않은 내용은 추측하지 말고 검색 도구를 사용하거나 모른다고 답변하세요.

**[Output Style]**
- 한국어로 답변할 것.
- 전문적이고 신뢰감 있는 어조를 유지할 것.
- 목차는 마크다운 표(Table) 형식을 사용할 것.
- JSON 형식으로 응답할 것.

**[절대 금지 표현 - 매우 중요]**
다음 표현들은 절대 사용하지 마세요. 위반 시 응답이 거부됩니다:
- "이 콘텐츠", "이 영상", "이 비디오", "해당 영상", "본 영상", "이 동영상" 등
- "이 섹션", "해당 섹션", "본 섹션", "이 부분" 등
- "첫 번째 섹션", "마지막 섹션", "다음 섹션", "이전 섹션" 등 섹션 순서 언급
- "앞서", "뒤에서", "이전에", "다음에", "나중에" 등 순서 참조 표현
- "섹션 N", "N번 섹션", "N번째 섹션" 등 섹션 번호 참조
- 대신 구체적인 내용을 직접 설명하세요. 예: "이 섹션에서는..." ❌ → "마케팅의 정의와 중요성을 다룹니다" ✅
"""


import requests as http_requests  # requests 라이브러리 import


def is_youtube_url(url: str) -> bool:
    """URL이 YouTube URL인지 확인"""
    youtube_patterns = [
        'youtube.com/watch',
        'youtu.be/',
        'youtube.com/embed/',
        'youtube.com/shorts/',
        'youtube.com/live/'
    ]
    return any(pattern in url for pattern in youtube_patterns)


def is_direct_video_url(url: str) -> bool:
    """URL이 직접 비디오 파일 URL인지 확인"""
    video_extensions = ['.mp4', '.webm', '.mkv', '.avi', '.mov', '.m4v', '.flv']
    url_lower = url.lower().split('?')[0]  # 쿼리 파라미터 제거
    return any(url_lower.endswith(ext) for ext in video_extensions)


def download_direct_video(url: str) -> str:
    """직접 비디오 URL에서 비디오 다운로드 (MP4, WebM 등)"""
    temp_video = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
    temp_video_path = temp_video.name
    temp_video.close()
    
    try:
        print(f"직접 비디오 URL 다운로드 시작: {url}")
        
        # 스트리밍 다운로드
        response = http_requests.get(url, stream=True, timeout=60, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()
        
        # 파일에 쓰기
        with open(temp_video_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # 파일 검증
        file_size = os.path.getsize(temp_video_path)
        if file_size == 0:
            raise Exception("다운로드된 파일이 비어있습니다")
        
        if file_size < 1024:  # 1KB 미만
            raise Exception(f"다운로드된 파일이 너무 작습니다 ({file_size} bytes)")
        
        print(f"직접 비디오 다운로드 완료: {temp_video_path} ({file_size} bytes)")
        return temp_video_path
        
    except Exception as e:
        # 실패 시 임시 파일 정리
        if os.path.exists(temp_video_path):
            try:
                os.unlink(temp_video_path)
            except:
                pass
        raise Exception(f"비디오 다운로드 실패: {str(e)}")


def download_youtube_video(url: str) -> str:
    """YouTube 비디오 다운로드"""
    temp_video = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
    temp_video_path = temp_video.name
    temp_video.close()
    
    try:
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': temp_video_path,
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4',  # 비디오+오디오 병합
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # 파일이 완전히 다운로드되었는지 확인
        max_wait = 10  # 최대 10초 대기
        wait_count = 0
        while wait_count < max_wait:
            if os.path.exists(temp_video_path) and os.path.getsize(temp_video_path) > 0:
                # 파일 크기가 안정화될 때까지 대기 (1초 동안 크기 변화 없음)
                size1 = os.path.getsize(temp_video_path)
                time.sleep(1)
                size2 = os.path.getsize(temp_video_path)
                if size1 == size2 and size1 > 1024:  # 최소 1KB 이상
                    break
            time.sleep(0.5)
            wait_count += 0.5
        
        # 파일 검증
        if not os.path.exists(temp_video_path):
            raise Exception("다운로드된 파일이 존재하지 않습니다")
        
        file_size = os.path.getsize(temp_video_path)
        if file_size == 0:
            raise Exception("다운로드된 파일이 비어있습니다")
        
        if file_size < 1024:  # 1KB 미만
            raise Exception(f"다운로드된 파일이 너무 작습니다 ({file_size} bytes)")
        
        print(f"YouTube 다운로드 완료: {temp_video_path} ({file_size} bytes)")
        return temp_video_path
    except Exception as e:
        # 실패 시 임시 파일 정리
        if os.path.exists(temp_video_path):
            try:
                os.unlink(temp_video_path)
            except:
                pass
        raise Exception(f"YouTube 다운로드 실패: {str(e)}")


def download_video(url: str) -> str:
    """URL 유형에 따라 적절한 다운로드 방식 선택"""
    if is_youtube_url(url):
        print(f"YouTube URL 감지: {url}")
        return download_youtube_video(url)
    elif is_direct_video_url(url):
        print(f"직접 비디오 URL 감지: {url}")
        return download_direct_video(url)
    else:
        # 그 외의 경우 yt-dlp로 시도 (다양한 사이트 지원)
        print(f"기타 URL, yt-dlp로 시도: {url}")
        try:
            return download_youtube_video(url)
        except:
            # yt-dlp 실패 시 직접 다운로드 시도
            print("yt-dlp 실패, 직접 다운로드 시도...")
            return download_direct_video(url)


def extract_audio_from_video(video_path: str) -> tuple:
    """비디오에서 오디오 추출 및 duration 반환"""
    # 파일 검증
    if not os.path.exists(video_path):
        raise Exception(f"비디오 파일이 존재하지 않습니다: {video_path}")
    
    file_size = os.path.getsize(video_path)
    if file_size == 0:
        raise Exception(f"비디오 파일이 비어있습니다: {video_path}")
    
    print(f"오디오 추출 시작: {video_path} ({file_size} bytes)")
    
    temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
    temp_audio_path = temp_audio.name
    temp_audio.close()
    
    try:
        # MoviePy가 파일을 읽을 수 있는지 먼저 확인
        print("비디오 파일 로딩 중...")
        video = VideoFileClip(video_path)
        
        # duration 확인
        if video.duration is None or video.duration <= 0:
            video.close()
            raise Exception("비디오 duration을 읽을 수 없습니다. 파일이 손상되었을 수 있습니다.")
        
        video_duration = video.duration
        print(f"비디오 duration: {video_duration}초")
        
        # 오디오 추출
        if video.audio is None:
            video.close()
            raise Exception("비디오에 오디오 트랙이 없습니다")
        
        print("오디오 추출 중...")
        audio = video.audio
        # 모노로 변환하고 낮은 비트레이트 사용 (음성 인식에 충분함)
        audio.write_audiofile(
            temp_audio_path, 
            verbose=False, 
            logger=None,
            codec='mp3',
            bitrate='64k',  # 64kbps로 낮춤 (음성 인식에 충분)
            ffmpeg_params=['-ac', '1']  # 모노로 변환 (크기 절반)
        )
        audio.close()
        video.close()
        
        # 오디오 파일 검증
        if not os.path.exists(temp_audio_path) or os.path.getsize(temp_audio_path) == 0:
            raise Exception("오디오 추출 실패: 생성된 파일이 비어있습니다")
        
        audio_size = os.path.getsize(temp_audio_path)
        print(f"오디오 추출 완료: {temp_audio_path} ({audio_size} bytes, {audio_size / 1024 / 1024:.2f} MB)")
        return temp_audio_path, video_duration
    except Exception as e:
        # 실패 시 임시 파일 정리
        if os.path.exists(temp_audio_path):
            try:
                os.unlink(temp_audio_path)
            except:
                pass
        raise Exception(f"오디오 추출 실패: {str(e)}")


def split_audio_for_whisper(audio_path: str, max_size_mb: int = 24) -> list:
    """
    오디오 파일이 Whisper API 제한(25MB)을 초과하면 청크로 분할 (moviepy 사용)
    
    Returns:
        [(chunk_path, start_time), ...] 리스트
    """
    from moviepy.editor import AudioFileClip
    
    file_size = os.path.getsize(audio_path)
    max_size_bytes = max_size_mb * 1024 * 1024
    
    if file_size <= max_size_bytes:
        return [(audio_path, 0)]
    
    print(f"오디오 파일이 {file_size / 1024 / 1024:.2f}MB로 제한 초과. 청킹 시작...")
    
    # 오디오 로드
    audio = AudioFileClip(audio_path)
    duration_sec = audio.duration
    
    # 파일 크기 기반으로 청크 수 계산 (약간의 여유 두고)
    num_chunks = int(file_size / max_size_bytes) + 1
    chunk_duration_sec = duration_sec / num_chunks
    
    chunks = []
    for i in range(num_chunks):
        start_sec = i * chunk_duration_sec
        end_sec = min((i + 1) * chunk_duration_sec, duration_sec)
        
        # 청크 추출
        chunk = audio.subclip(start_sec, end_sec)
        
        # 청크 파일 저장
        chunk_path = audio_path.replace('.mp3', f'_chunk{i}.mp3')
        chunk.write_audiofile(
            chunk_path,
            verbose=False,
            logger=None,
            codec='mp3',
            bitrate='64k',
            ffmpeg_params=['-ac', '1']
        )
        chunk.close()
        
        chunk_size = os.path.getsize(chunk_path)
        print(f"청크 {i+1}/{num_chunks}: {start_sec:.1f}s - {end_sec:.1f}s ({chunk_size / 1024 / 1024:.2f}MB)")
        
        chunks.append((chunk_path, start_sec))
    
    audio.close()
    return chunks


def whisper_transcribe(audio_path: str) -> dict:
    """OpenAI Whisper API로 음성을 텍스트로 변환 (대용량 파일 자동 청킹)"""
    try:
        # 파일 크기 확인 및 필요시 청킹
        chunks = split_audio_for_whisper(audio_path)
        
        all_text = []
        all_segments = []
        
        for chunk_idx, (chunk_path, time_offset) in enumerate(chunks):
            print(f"Whisper 처리 중... ({chunk_idx + 1}/{len(chunks)})")
            
            with open(chunk_path, 'rb') as audio_file:
                transcript = openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    language="ko"
                )
            
            all_text.append(transcript.text)
            
            # 세그먼트에 시간 오프셋 추가
            for seg in getattr(transcript, 'segments', []):
                all_segments.append({
                    'start': getattr(seg, 'start', 0) + time_offset,
                    'end': getattr(seg, 'end', 0) + time_offset,
                    'text': getattr(seg, 'text', '')
                })
            
            # 청크 파일 정리 (원본 제외)
            if chunk_path != audio_path:
                try:
                    os.unlink(chunk_path)
                except:
                    pass
        
        return {
            'text': ' '.join(all_text),
            'segments': all_segments
        }
    except Exception as e:
        raise Exception(f"Whisper STT 실패: {str(e)}")


def extract_frames_at_timestamps(video_path: str, timestamps: list, max_width: int = 800) -> list:
    """
    비디오에서 특정 타임스탬프의 프레임을 추출하여 Base64로 반환
    
    Args:
        video_path: 비디오 파일 경로
        timestamps: 추출할 타임스탬프 리스트 (초 단위)
        max_width: 이미지 최대 너비 (리사이즈용)
    
    Returns:
        [{ "timestamp": float, "imageBase64": str, "width": int, "height": int }]
    """
    frames = []
    
    try:
        video = VideoFileClip(video_path)
        duration = video.duration
        
        for ts in timestamps:
            try:
                # 타임스탬프가 비디오 길이를 초과하면 스킵
                if ts >= duration or ts < 0:
                    continue
                
                # 프레임 추출
                frame = video.get_frame(ts)
                
                # numpy array를 PIL Image로 변환
                img = Image.fromarray(frame)
                
                # 리사이즈 (가로 기준)
                if img.width > max_width:
                    ratio = max_width / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                
                # Base64로 인코딩
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=85)
                img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                
                frames.append({
                    'timestamp': ts,
                    'imageBase64': img_base64,
                    'width': img.width,
                    'height': img.height
                })
                
            except Exception as e:
                print(f"프레임 추출 실패 (timestamp={ts}): {e}")
                continue
        
        video.close()
        
    except Exception as e:
        print(f"비디오 프레임 추출 실패: {e}")
    
    return frames


def extract_uniform_frames(video_path: str, num_frames: int = 10, max_width: int = 800) -> list:
    """
    비디오에서 균등 간격으로 프레임을 추출
    
    Args:
        video_path: 비디오 파일 경로
        num_frames: 추출할 프레임 수
        max_width: 이미지 최대 너비
    
    Returns:
        프레임 리스트
    """
    try:
        video = VideoFileClip(video_path)
        duration = video.duration
        video.close()
        
        # 균등 간격 타임스탬프 계산
        timestamps = []
        for i in range(num_frames):
            ts = (i + 0.5) * duration / num_frames  # 각 구간의 중간점
            timestamps.append(ts)
        
        return extract_frames_at_timestamps(video_path, timestamps, max_width)
        
    except Exception as e:
        print(f"균등 프레임 추출 실패: {e}")
        return []


def upload_video_to_gemini(video_path: str) -> str:
    """Gemini File API를 사용하여 비디오 업로드"""
    try:
        # 파일 업로드
        video_file = genai.upload_file(path=video_path)
        return video_file.uri
    except Exception as e:
        raise Exception(f"Gemini 파일 업로드 실패: {str(e)}")


def analyze_with_gemini(video_uri: str, transcript: dict, video_duration: float = None) -> dict:
    """Gemini로 비디오와 스크립트를 함께 분석 (주요 프레임 타임스탬프 포함)"""
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        # 스크립트 포맷팅
        transcript_text = transcript['text']
        segments_text = '\n'.join([
            f"[{int(seg['start']//60):02d}:{int(seg['start']%60):02d}] {seg['text']}"
            for seg in transcript.get('segments', [])
        ])
        
        duration_info = f"비디오 길이: {int(video_duration // 60)}분 {int(video_duration % 60)}초" if video_duration else ""
        
        prompt = f"""{SYSTEM_PROMPT}

## 비디오 정보
비디오 파일이 첨부되어 있습니다.
{duration_info}

## 음성 스크립트 (Whisper)
{transcript_text}

## 타임스탬프별 세그먼트
{segments_text}

위 비디오와 스크립트를 분석하여 다음 JSON 형식으로 응답해주세요:

**[중요 지시사항]**
1. **지시대명사 절대 금지**: "이 콘텐츠", "이 영상", "이 섹션", "해당", "본" 등의 표현을 절대 사용하지 마세요.
2. **구체적 서술**: 제목과 설명은 실제 다루는 내용을 구체적으로 명시하세요.
   - ❌ "이 섹션에서는 마케팅을 소개합니다"
   - ✅ "마케팅의 정의와 핵심 개념"
3. **순서 참조 금지**: "첫 번째", "마지막", "다음", "이전" 등의 순서 표현 사용 금지
4. **섹션 번호 금지**: "섹션 1", "1번 섹션" 등의 번호 참조 금지

**[요약 지침 - 매우 중요]**
- 요약(summary)은 내용의 분량과 복잡도에 맞게 충분히 상세하게 작성하세요.
- 줄 수 제한 없이, 핵심 개념, 주요 논점, 결론, 실용적 조언 등을 모두 포함하세요.
- 나중에 참조 자료로 활용할 수 있을 정도로 정밀하고 정확하게 작성하세요.
- 중요한 수치, 사례, 방법론 등 구체적인 정보를 포함하세요.

**[키워드 지침]**
- 각 키워드는 "키워드: 한줄 설명" 형식으로 작성하세요.
- 예: "SEO: 검색엔진 최적화로 웹사이트 노출을 높이는 마케팅 기법"

**[주요 프레임 식별 - 중요] ★NEW★**
- 비디오에서 시각적으로 중요한 장면의 타임스탬프를 식별하세요.
- 다이어그램, 차트, 슬라이드, 도표, 코드, 중요 텍스트가 표시된 장면을 찾으세요.
- 각 섹션별로 가장 대표적인 시각 자료가 나오는 순간을 선택하세요.
- 최소 3개, 최대 8개의 주요 프레임을 식별하세요.
- timestampSeconds는 반드시 초 단위 숫자로 입력하세요.

**JSON 형식:**
{{
  "summary": "상세하고 정밀한 요약. 줄 수 제한 없이 핵심 내용을 모두 포함.",
  "tableOfContents": [
    {{
      "timestamp": "00:00",
      "timestampSeconds": 0,
      "title": "구체적인 섹션 제목",
      "description": "구체적인 섹션 설명",
      "summary": "상세 요약",
      "keyPoints": ["포인트1", "포인트2", "포인트3"]
    }}
  ],
  "keywords": ["키워드1: 한줄 설명", "키워드2: 한줄 설명"],
  "keyInsights": ["인사이트1", "인사이트2"],
  "difficulty": "beginner|intermediate|advanced",
  "category": "카테고리",
  "keyFrames": [
    {{
      "timestampSeconds": 30,
      "timestamp": "00:30",
      "description": "프레임에 표시된 내용 설명 (예: 마케팅 4P 전략 다이어그램)",
      "type": "diagram|chart|slide|code|screenshot|scene",
      "relatedSection": "관련 섹션 제목"
    }}
  ]
}}"""
        
        # 비디오 파일 참조
        video_file = genai.get_file(video_uri.split('/')[-1])
        
        response = model.generate_content(
            [prompt, video_file],
            generation_config={
                'temperature': 0.2,
                'max_output_tokens': 8000,
                'response_mime_type': 'application/json'
            }
        )
        
        # JSON 파싱
        result = json.loads(response.text)
        return result
        
    except Exception as e:
        raise Exception(f"Gemini 분석 실패: {str(e)}")


def search_internet(query: str) -> str:
    """인터넷 검색 (Tavily API 또는 Google Search)"""
    if tavily_client:
        try:
            results = tavily_client.search(query, max_results=3)
            if results and 'results' in results:
                summary = '\n'.join([
                    f"- {r.get('title', '')}: {r.get('content', '')[:200]}..."
                    for r in results['results'][:3]
                ])
                return summary
        except Exception as e:
            print(f"Tavily 검색 실패: {e}")
    
    # Tavily가 없으면 빈 문자열 반환 (나중에 Google Search로 확장 가능)
    return ""


@app.route('/health', methods=['GET'])
def health():
    """헬스 체크"""
    return jsonify({'status': 'ok'})


@app.route('/analyze', methods=['POST'])
def analyze_video():
    """비디오 분석 엔드포인트 (주요 프레임 추출 포함)"""
    try:
        temp_video_path = None
        
        # Content-Type 확인
        content_type = request.content_type or ''
        
        # URL 처리 (JSON) - YouTube, 직접 MP4 등 모든 비디오 URL 지원
        if 'application/json' in content_type:
            try:
                data = request.get_json()
                if not data or 'url' not in data:
                    return jsonify({'error': '비디오 URL이 필요합니다'}), 400
                
                video_url = data['url']
                print(f"비디오 URL 다운로드: {video_url}")
                temp_video_path = download_video(video_url)
            except Exception as e:
                return jsonify({'error': f'비디오 다운로드 실패: {str(e)}'}), 400
        
        # 파일 업로드 처리 (multipart/form-data)
        elif 'video' in request.files:
            video_file = request.files['video']
            if video_file.filename == '':
                return jsonify({'error': '파일명이 없습니다'}), 400
            
            temp_video = tempfile.NamedTemporaryFile(delete=False, suffix=Path(video_file.filename).suffix)
            temp_video_path = temp_video.name
            video_file.save(temp_video_path)
            temp_video.close()
        else:
            return jsonify({'error': '비디오 파일 또는 YouTube URL이 필요합니다'}), 400
        
        try:
            # 1. 오디오 추출 + duration 가져오기
            print("오디오 추출 중...")
            audio_path, video_duration = extract_audio_from_video(temp_video_path)
            
            # 2. Whisper STT
            print("Whisper STT 중...")
            transcript = whisper_transcribe(audio_path)
            
            # 3. Gemini에 비디오 업로드
            print("Gemini에 비디오 업로드 중...")
            video_uri = upload_video_to_gemini(temp_video_path)
            
            # 4. Gemini 분석 (duration 포함)
            print("Gemini 분석 중...")
            analysis = analyze_with_gemini(video_uri, transcript, video_duration)
            
            # 5. Gemini가 식별한 주요 프레임 추출
            key_frames_with_images = []
            if 'keyFrames' in analysis and analysis['keyFrames']:
                print(f"주요 프레임 {len(analysis['keyFrames'])}개 추출 중...")
                
                # Gemini가 식별한 타임스탬프 추출
                timestamps = [
                    kf.get('timestampSeconds', 0) 
                    for kf in analysis['keyFrames'] 
                    if isinstance(kf.get('timestampSeconds'), (int, float))
                ]
                
                # 프레임 추출
                extracted_frames = extract_frames_at_timestamps(temp_video_path, timestamps)
                
                # 메타데이터와 이미지 결합
                for i, kf in enumerate(analysis['keyFrames']):
                    ts = kf.get('timestampSeconds', 0)
                    # 해당 타임스탬프의 이미지 찾기
                    matched_frame = next(
                        (f for f in extracted_frames if abs(f['timestamp'] - ts) < 1),
                        None
                    )
                    
                    frame_data = {
                        'timestamp': kf.get('timestamp', '00:00'),
                        'timestampSeconds': ts,
                        'description': kf.get('description', ''),
                        'type': kf.get('type', 'scene'),
                        'relatedSection': kf.get('relatedSection', '')
                    }
                    
                    if matched_frame:
                        frame_data['imageBase64'] = matched_frame['imageBase64']
                        frame_data['width'] = matched_frame['width']
                        frame_data['height'] = matched_frame['height']
                    
                    key_frames_with_images.append(frame_data)
                
                print(f"프레임 추출 완료: {len(key_frames_with_images)}개")
            
            # 6. 결과 반환 (이미지 포함)
            return jsonify({
                'success': True,
                'transcript': transcript,
                'analysis': analysis,
                'keyFrames': key_frames_with_images,
                'duration': video_duration
            })
            
        finally:
            # 임시 파일 정리
            if os.path.exists(temp_video_path):
                os.unlink(temp_video_path)
            if 'audio_path' in locals() and os.path.exists(audio_path):
                os.unlink(audio_path)
                
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/qa', methods=['POST'])
def question_answer():
    """질의응답 엔드포인트"""
    try:
        data = request.json
        question = data.get('question')
        transcript = data.get('transcript')
        analysis = data.get('analysis')
        
        if not question:
            return jsonify({'error': '질문이 없습니다'}), 400
        
        # 내부 데이터에서 답 찾기
        context = f"""
## 비디오 요약
{analysis.get('summary', '')}

## 목차
{json.dumps(analysis.get('tableOfContents', []), ensure_ascii=False, indent=2)}

## 전체 스크립트
{transcript.get('text', '')}
"""
        
        # Gemini로 질문 답변
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        prompt = f"""{SYSTEM_PROMPT}

## 비디오 분석 결과
{context}

## 사용자 질문
{question}

**[답변 규칙]**
1. 비디오 내용에 답이 있으면 "영상 내용에 따르면..."으로 시작하고, 없으면 "영상에는 언급되지 않았으나..."로 시작
2. **절대 금지 표현**: "이 콘텐츠", "이 영상", "이 섹션", "해당", "본", "첫 번째", "마지막", "다음", "이전" 등 지시대명사나 순서 참조 표현 사용 금지
3. 구체적인 내용을 직접 설명하세요. 예: "이 섹션에서는..." ❌ → "마케팅의 정의와 중요성을 다룹니다" ✅
4. 자연스러운 대화체로 답변하되, 지시대명사는 절대 사용하지 마세요.

**[주제 제한 규칙 - 매우 중요]**
- 당신은 오직 분석된 비디오 내용과 관련된 질문에만 답변해야 합니다.
- 비디오 내용과 완전히 관련 없는 질문(예: 날씨, 개인적인 조언, 다른 주제 등)에는 정중하게 거절하세요.
- 거절 시 다음과 같이 답변: "죄송합니다. 저는 분석된 비디오 내용에 대한 질문에만 답변할 수 있습니다. [비디오 주제]와 관련된 질문을 해주세요."
- 비디오 주제와 조금이라도 관련이 있다면 답변을 시도하되, 완전히 동떨어진 주제는 거절하세요.
"""
        
        # 먼저 내부 데이터로 답변 시도
        response = model.generate_content(
            prompt,
            generation_config={
                'temperature': 0.7,
                'max_output_tokens': 2000
            }
        )
        
        answer = response.text
        
        # 내부 데이터에 답이 없거나 부족하면 인터넷 검색
        if '언급되지 않았으나' in answer or '확인 결과' in answer:
            search_results = search_internet(question)
            if search_results:
                answer += f"\n\n## 추가 정보 (인터넷 검색)\n{search_results}"
        
        return jsonify({
            'success': True,
            'answer': answer
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
