"""
Video Analysis Backend Server
OpenAI Whisper + Gemini 2.5 Flash 하이브리드 분석 시스템
"""

import os
import json
import tempfile
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import openai
import google.generativeai as genai
from moviepy.editor import VideoFileClip
import tavily
import yt_dlp

# 환경 변수 로드
load_dotenv()

app = Flask(__name__)
CORS(app)  # Chrome Extension에서 호출 가능하도록 CORS 허용

# API 키 설정
openai.api_key = os.getenv('OPENAI_API_KEY')
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
"""


def download_youtube_video(url: str) -> str:
    """YouTube 비디오 다운로드"""
    temp_video = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
    temp_video_path = temp_video.name
    temp_video.close()
    
    try:
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': temp_video_path,
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return temp_video_path
    except Exception as e:
        raise Exception(f"YouTube 다운로드 실패: {str(e)}")


def extract_audio_from_video(video_path: str) -> str:
    """비디오에서 오디오 추출"""
    temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
    temp_audio_path = temp_audio.name
    temp_audio.close()
    
    try:
        video = VideoFileClip(video_path)
        audio = video.audio
        audio.write_audiofile(temp_audio_path, verbose=False, logger=None)
        audio.close()
        video.close()
        return temp_audio_path
    except Exception as e:
        raise Exception(f"오디오 추출 실패: {str(e)}")


def whisper_transcribe(audio_path: str) -> dict:
    """OpenAI Whisper API로 음성을 텍스트로 변환"""
    try:
        with open(audio_path, 'rb') as audio_file:
            transcript = openai.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                language="ko"
            )
        return {
            'text': transcript.text,
            'segments': [
                {
                    'start': seg.get('start', 0),
                    'end': seg.get('end', 0),
                    'text': seg.get('text', '')
                }
                for seg in getattr(transcript, 'segments', [])
            ]
        }
    except Exception as e:
        raise Exception(f"Whisper STT 실패: {str(e)}")


def upload_video_to_gemini(video_path: str) -> str:
    """Gemini File API를 사용하여 비디오 업로드"""
    try:
        # 파일 업로드
        video_file = genai.upload_file(path=video_path)
        return video_file.uri
    except Exception as e:
        raise Exception(f"Gemini 파일 업로드 실패: {str(e)}")


def analyze_with_gemini(video_uri: str, transcript: dict) -> dict:
    """Gemini로 비디오와 스크립트를 함께 분석"""
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        # 스크립트 포맷팅
        transcript_text = transcript['text']
        segments_text = '\n'.join([
            f"[{int(seg['start']//60):02d}:{int(seg['start']%60):02d}] {seg['text']}"
            for seg in transcript.get('segments', [])
        ])
        
        prompt = f"""{SYSTEM_PROMPT}

## 비디오 정보
비디오 파일이 첨부되어 있습니다.

## 음성 스크립트 (Whisper)
{transcript_text}

## 타임스탬프별 세그먼트
{segments_text}

위 비디오와 스크립트를 분석하여 다음 JSON 형식으로 응답해주세요:
{{
  "summary": "상세 요약 (3-5문장)",
  "tableOfContents": [
    {{
      "timestamp": "00:00",
      "title": "섹션 제목",
      "description": "섹션 설명",
      "summary": "상세 요약",
      "keyPoints": ["포인트1", "포인트2"]
    }}
  ],
  "keywords": ["키워드1", "키워드2"],
  "keyInsights": ["인사이트1", "인사이트2"],
  "difficulty": "beginner|intermediate|advanced",
  "category": "카테고리"
}}
"""
        
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
    """비디오 분석 엔드포인트"""
    try:
        temp_video_path = None
        
        # Content-Type 확인
        content_type = request.content_type or ''
        
        # YouTube URL 처리 (JSON)
        if 'application/json' in content_type:
            try:
                data = request.get_json()
                if not data or 'url' not in data:
                    return jsonify({'error': 'YouTube URL이 필요합니다'}), 400
                
                youtube_url = data['url']
                print(f"YouTube URL 다운로드: {youtube_url}")
                temp_video_path = download_youtube_video(youtube_url)
            except Exception as e:
                return jsonify({'error': f'JSON 파싱 실패: {str(e)}'}), 400
        
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
            # 1. 오디오 추출
            print("오디오 추출 중...")
            audio_path = extract_audio_from_video(temp_video_path)
            
            # 2. Whisper STT
            print("Whisper STT 중...")
            transcript = whisper_transcribe(audio_path)
            
            # 3. Gemini에 비디오 업로드
            print("Gemini에 비디오 업로드 중...")
            video_uri = upload_video_to_gemini(temp_video_path)
            
            # 4. Gemini 분석
            print("Gemini 분석 중...")
            analysis = analyze_with_gemini(video_uri, transcript)
            
            # 결과 반환
            return jsonify({
                'success': True,
                'transcript': transcript,
                'analysis': analysis
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

위 비디오 내용을 기반으로 질문에 답변해주세요. 
비디오 내용에 답이 있으면 "영상 내용에 따르면..."으로 시작하고,
없으면 "영상에는 언급되지 않았으나..."로 시작하여 인터넷 검색 결과를 포함해주세요.
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

