"""구술 PDF에서 원문을 추출하고, 사람이 검토한 찬반 코딩을 결합합니다.
실행: pip install pymupdf && python build_data.py
분류는 연구자의 질적 판단이므로 근거 없는 감성분석 결과로 표시하지 않습니다.
"""
from __future__ import annotations
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
PDF = DATA / 'source.pdf'


def parse_pdf(pdf=PDF):
    import fitz  # PyMuPDF: 재생성할 때만 필요
    result = []
    region = None
    current = None
    with fitz.open(pdf) as doc:
        for page_number, page in enumerate(doc, start=1):
            for original_line in page.get_text().splitlines(keepends=False):
                line = original_line.strip()
                if not line:
                    continue
                m = re.fullmatch(r'[123]\.\s*(정릉동|길음동|장위동)', line)
                if m:
                    region = m.group(1)
                    continue
                starts_record = line.startswith('○') or line.startswith('장위 4구역에서')
                if starts_record:
                    if current is not None:
                        raise ValueError(f'이전 기록의 화자 정보가 없습니다: {current}')
                    current = {'id':len(result)+1, 'region':region, 'start_page':page_number, 'end_page':page_number, 'parts': []}
                    line = line.lstrip('○').lstrip()
                if current is None:
                    continue
                current['end_page'] = page_number
                if line.startswith('-'):
                    current['speaker'] = line[1:].strip().rstrip(',')
                    current['full_text'] = ''.join(current.pop('parts')).strip()
                    result.append(current)
                    current = None
                else:
                    # 원문 PDF의 한글 음절 단위 줄바꿈은 단어 사이에 공백을 추가하지 않습니다.
                    # PDF 행 끝에 이미 있는 공백은 원본 그대로 유지합니다.
                    current['parts'].append(original_line.lstrip('○').lstrip() if starts_record else original_line.lstrip())
    if current:
        raise ValueError('마지막 구술 항목의 출처 표기를 찾지 못했습니다.')
    return result


def build():
    records = parse_pdf()
    manual = json.loads((DATA / 'annotations.json').read_text(encoding='utf-8'))
    if len(records) != 14 or len(manual) != 14:
        raise ValueError(f'구술 항목 수 불일치: PDF {len(records)}개, 주석 {len(manual)}개')
    for rec in records:
        annotation = manual[str(rec['id'])]
        if rec['region'] != annotation['region']:
            raise ValueError(f"#{rec['id']} 지역 정보 불일치")
        for point in annotation['points']:
            if point['stance'] not in ('긍정', '부정'):
                raise ValueError('분류는 긍정 또는 부정만 허용합니다')
            if point['excerpt'] not in rec['full_text']:
                raise ValueError(f"#{rec['id']} 원문에 없는 인용: {point['excerpt']}")
        rec.update(annotation)
        rec['stances'] = list(dict.fromkeys(p['stance'] for p in rec['points']))
        rec['source'] = '사조방 구술 자료 2.pdf'
    with (DATA / 'classified_quotes.csv').open('w', encoding='utf-8-sig', newline='') as fp:
        writer = csv.DictWriter(fp, fieldnames=['record_id','region','speaker','pages','stance','theme','excerpt','title'])
        writer.writeheader()
        for r in records:
            for pt in r['points']:
                writer.writerow({'record_id':r['id'],'region':r['region'],'speaker':r['speaker'],'pages':f"{r['start_page']}-{r['end_page']}",'stance':pt['stance'],'theme':pt['theme'],'excerpt':pt['excerpt'],'title':r['title']})
    outfile = DATA / 'records.json'
    outfile.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {
        region: {'records':sum(r['region'] == region for r in records),
                 '긍정':sum(r['region'] == region and '긍정' in r['stances'] for r in records),
                 '부정':sum(r['region'] == region and '부정' in r['stances'] for r in records)}
        for region in ('정릉동','길음동','장위동')
    }
    print(f'생성 완료: {outfile}\n{json.dumps(summary, ensure_ascii=False, indent=2)}')
    return records

if __name__ == '__main__':
    build()
