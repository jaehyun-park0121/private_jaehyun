import re
import os
import shutil

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None
    print("PyMuPDF(fitz) 라이브러리가 설치되지 않았습니다. 'pip install PyMuPDF'를 실행해주십시오.")


class ScientificPDFAnalyzer:
    """과학기술 문서(특허, 논문, 보고서) 심층 필터링 클래스"""
    
    # 핵심 키워드 사전 (가중치 부여용)
    SCIENCE_KEYWORDS = [
        "청구항", "실시예", "명세서", "도면", "목적", "발명의", # 특허 및 공학
        "화학식", "반응식", "중량부", "조성물", "분자량", "수용액", "wt%", "mol",  # 화학
        "수식", "방정식", "알고리즘", "파라미터", "시뮬레이션", "그래프", "오차", # 수학/컴퓨터/통계
        "본론", "초록", "abstract", "결과 및 고찰", "결언", "참고문헌" # 논문/보고서 구조
    ]
    
    # 공공누리 및 오픈액세스 라이선스 키워드 (저작권 필터링용)
    LICENSE_KEYWORDS = [
        "공공누리", "제1유형", "제0유형", "출처표시", "오픈액세스", "open access", "kogl", "ai 학습 허용"
    ]
    
    # 텍스트가 아닌 이미지 마크업일 확률이 높으므로 기본값은 False로 둡니다.
    def __init__(self, min_keyword_score=3, require_license=False):
        self.min_keyword_score = min_keyword_score
        self.require_license = require_license

    def analyze_pdf(self, pdf_path):
        """
        단일 PDF 파일을 심사합니다.
        
        Returns:
            dict: 심사 결과 요약본 및 통과 여부('passed')
        """
        if not fitz:
            return {"error": "PyMuPDF not installed", "passed": False}
            
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            return {"error": f"파일 손상 또는 접근 불가: {str(e)}", "passed": False}
            
        # 기본 정보
        num_pages = len(doc)
        if num_pages == 0:
            return {"error": "빈 PDF", "passed": False}
        
        # 1. Digital Born 및 한국어 판별을 위한 텍스트 추출
        total_text = ""
        total_korean_chars = 0
        total_chars = 0
        
        # 2. 멀티 모달리티 (표, 차트, 이미지 융합) 판별
        has_multimodal_page = False
        multimodal_page_details = []
        
        # 성능을 위해 최대 50페이지만 스캔
        pages_to_scan = min(num_pages, 50)
        
        for i in range(pages_to_scan):
            page = doc[i]
            
            # --- Text 레이어 검사 ---
            text = page.get_text()
            total_text += text + "\n"
            
            clamped_text = text.strip()
            total_chars += len(clamped_text)
            kor_matches = re.findall(r'[가-힣]', clamped_text)
            total_korean_chars += len(kor_matches)
            
            # --- 2종 이상 시각 모달리티 공존 검사 ---
            # Text는 기본으로 깔려있다고 가정하고, (표 + 이미지) 또는 (표 + 차트/도형) 여부 검사
            try:
                images_count = len(page.get_images())
                tables_count = len(page.find_tables().tables) if hasattr(page, 'find_tables') else 0
                drawings_count = len(page.get_drawings()) # 일러스트, 캐드, 차트 등의 벡터 도형
                
                # 시각 요소 3개 중 2개 이상이 0보다 크면 다중 모달리티 페이지로 판정!
                modal_count = sum([1 for x in [images_count, tables_count, drawings_count] if x > 0])
                if modal_count >= 2:
                    has_multimodal_page = True
                    multimodal_page_details.append(f"P.{i+1} (표 {tables_count}, 이미지 {images_count}, 벡터도형 {drawings_count})")
            except Exception:
                pass

        doc.close()

        # 조건 1: Digital Born (1페이지당 평균 100자 이상의 텍스트가 인식 가능해야 함)
        avg_chars_per_page = total_chars / pages_to_scan
        is_digital_born = avg_chars_per_page > 100

        # 조건 2: 한국어 중심 문서 (한국어 글자 비율이 유효 문자열의 10% 이상인지)
        is_korean = (total_korean_chars / total_chars) > 0.1 if total_chars > 0 else False

        # 조건 3: 특허/화학/수학/논문 키워드 풍부함
        keyword_score = 0
        matched_keywords = []
        for kw in self.SCIENCE_KEYWORDS:
            count = total_text.count(kw)
            if count > 0:
                keyword_score += (1 if count < 3 else 2) # 등장이 잦으면 가중치
                matched_keywords.append(kw)
                
        is_science_doc = keyword_score >= self.min_keyword_score

        # 조건 4: 공공누리 0, 1유형 또는 오픈액세스 라이선스 명시 여부
        has_license = False
        total_text_lower = total_text.lower().replace(" ", "")
        if "공공누리" in total_text_lower or "kogl" in total_text_lower or "openaccess" in total_text_lower or "오픈액세스" in total_text_lower:
            # 공공누리라는 단어가 있을 경우, 1유형, 0유형, 출처표시 등의 단어가 같이 있는지 복합 검사
            if any(term in total_text_lower for term in ["1유형", "제1유형", "0유형", "제0유형", "출처표시", "ai학습"]):
                has_license = True
        elif not self.require_license:
            has_license = True # 라이선스 검사가 필수가 아니면 패스

        # 만약 공공데이터가 아닌 특허청/KDI 직링크 문서 등은 출처 자체가 보장이므로 예외 처리 기능이 추후 필요할 수 있음
        # 여기서는 강제로 검사
        if not self.require_license:
            has_license = True

        # 최종 합격 판단
        passed = is_digital_born and is_korean and has_multimodal_page and is_science_doc and has_license

        return {
            "passed": passed,
            "filename": os.path.basename(pdf_path),
            "stats": {
                "pages_scanned": pages_to_scan,
                "is_digital_born": is_digital_born,
                "is_korean": is_korean,
                "has_multimodal_page": has_multimodal_page,
                "is_science_doc": is_science_doc,
                "has_valid_license": has_license,
                "keyword_score": keyword_score
            },
            "details": {
                "avg_chars_per_page": int(avg_chars_per_page),
                "matched_keywords": matched_keywords[:5],
                "multimodal_pages": multimodal_page_details[:3] # 최대 3개만 샘플 출력
            }
        }

def filter_pdfs_in_directory(source_dir, output_dir):
    """
    지정된 디렉토리 안의 모든 PDF를 스캔하여 
    과학기술 데이터로 인정된 최상급 PDF만 output_dir로 복사합니다.
    """
    if not os.path.exists(source_dir):
        print(f"❌ 소스 폴더가 없습니다: {source_dir}")
        return

    os.makedirs(output_dir, exist_ok=True)
    analyzer = ScientificPDFAnalyzer(min_keyword_score=3)
    
    pdf_files = [f for f in os.listdir(source_dir) if f.lower().endswith('.pdf')]
    print(f"📥 총 {len(pdf_files)}개의 PDF 분석을 시작합니다...\n")
    
    passed_count = 0
    for idx, filename in enumerate(pdf_files, 1):
        filepath = os.path.join(source_dir, filename)
        
        result = analyzer.analyze_pdf(filepath)
        status = "✅ PASS" if result.get("passed") else "❌ FAIL"
        
        # 합격 시 복사
        if result.get("passed"):
            passed_count += 1
            shutil.copy2(filepath, os.path.join(output_dir, filename))
            
        print(f"[{idx}/{len(pdf_files)}] {status} : {filename}")
        if result.get("passed"):
            print(f"   ↳ [키워드 점수: {result['stats']['keyword_score']}] | [멀티모달 페이지: {', '.join(result['details']['multimodal_pages'])}]")
    
    print("\n" + "="*50)
    print(f"🎉 필터링 완료! 총 {len(pdf_files)}건 중 엄선된 문서: {passed_count}건")
    print(f"📁 저장된 위치: {output_dir}")
    print("="*50)


if __name__ == "__main__":
    # 임시 테스트용 실행
    import sys
    if len(sys.argv) > 2:
        filter_pdfs_in_directory(sys.argv[1], sys.argv[2])
    else:
        print("사용법: python pdf_analyzer.py <수집된_원본_폴더경로> <합격품질_저장할_폴더경로>")
