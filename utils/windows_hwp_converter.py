import os
import win32com.client as win32

def convert_hwp_to_docx(source_dir, output_dir):
    """
    지정된 폴더 안의 모든 HWP 파일을 찾아 DOCX로 일괄 변환(구조화)합니다.
    주의: 이 스크립트는 한컴오피스(한글)가 설치된 Windows 환경에서만 작동합니다.
    """
    if not os.path.exists(source_dir):
        print(f"❌ 소스 폴더가 없습니다: {source_dir}")
        return

    os.makedirs(output_dir, exist_ok=True)
    
    hwp_files = [f for f in os.listdir(source_dir) if f.lower().endswith('.hwp')]
    
    if not hwp_files:
        print("💡 변환할 HWP 파일이 없습니다.")
        return
        
    print(f"📥 한컴오피스를 백그라운드로 실행하여 {len(hwp_files)}개의 HWP 변환을 시작합니다...\n")

    try:
        # 한글 프로그램 백그라운드 실행
        hwp = win32.gencache.EnsureDispatch('HWPFrame.HwpObject')
        hwp.RegisterModule('FilePathCheckDLL', 'SecurityModule') # 보안 알림 무시 (설정 파일 필요 시)
        
        # 화면에 한글 창 숨기기
        hwp.XHwpWindows.Item(0).Visible = False
        
        success_count = 0
        for idx, filename in enumerate(hwp_files, 1):
            source_path = os.path.abspath(os.path.join(source_dir, filename))
            
            # 확장자를 docx로 변경하여 아웃풋 경로 생성
            base_name = os.path.splitext(filename)[0]
            output_filename = base_name + ".docx"
            output_path = os.path.abspath(os.path.join(output_dir, output_filename))
            
            try:
                # 파일 열기
                hwp.Open(source_path, "HWP", "force:True")
                
                # DOCX 포맷으로 저장 (형식 지정: "OOXML")
                hwp.SaveAs(output_path, "OOXML")
                success_count += 1
                print(f"[{idx}/{len(hwp_files)}] ✅ 성공: {filename} -> {output_filename}")
            except Exception as e:
                print(f"[{idx}/{len(hwp_files)}] ❌ 실패: {filename} ({str(e)})")
            finally:
                hwp.Clear(1) # 문서 닫기
                
    except Exception as e:
        print(f"❌ 한컴오피스(HWP) 자동화 구동 실패: {str(e)}")
        print("💡 (한글 오피스가 설치되어 있지 않거나, pywin32 패키지가 필요할 수 있습니다)")
    finally:
        try:
            hwp.Quit() # 한글 프로그램 종료
        except:
            pass
            
    print("\n" + "="*50)
    print(f"🎉 변환 완료! 총 {len(hwp_files)}건 중 DOCX 변환: {success_count}건")
    print(f"📁 저장된 위치: {output_dir}")
    print("="*50)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        convert_hwp_to_docx(sys.argv[1], sys.argv[2])
    else:
        print("사용법: python windows_hwp_converter.py <HWP가_있는_폴더> <DOCX_저장할_폴더>")
