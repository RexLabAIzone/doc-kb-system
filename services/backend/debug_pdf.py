from ebook_reader import extract_pdf_text
result = extract_pdf_text('/data/originals/心理学/房间里的大象：生活中的沉默和否认.pdf')
print(type(result))
print(repr(result))
print('len:', len(result))
