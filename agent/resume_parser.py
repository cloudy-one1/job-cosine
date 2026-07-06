"""简历文件解析 — 从 PDF / Word(.docx) 中提取纯文本。

支持格式:
  - .pdf  → PyPDF2 逐页提取
  - .docx → python-docx 段落提取

使用示例:
    from agent.resume_parser import extract_text

    text = extract_text(file_bytes, filename='resume.pdf')
    # text: 提取到的纯文本
"""

import io
import logging

_logger = logging.getLogger(__name__)


def extract_text(file_bytes: bytes, filename: str) -> str:
    """从上传的字节流中提取纯文本。

    Args:
        file_bytes: 上传文件的原始字节
        filename:   原始文件名（用于判断扩展名）

    Returns:
        提取到的纯文本；提取失败返回空字符串
    """
    fname = filename.lower().strip()

    if fname.endswith('.pdf'):
        return _from_pdf(file_bytes)
    elif fname.endswith('.docx'):
        return _from_docx(file_bytes)
    else:
        return ''


def _from_pdf(file_bytes: bytes) -> str:
    """PyPDF2 逐页提取 PDF 文本."""
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        _logger.warning('PyPDF2 未安装, 无法解析 PDF')
        return ''

    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        result = '\n'.join(pages)
        _logger.info('PDF 解析完成, 共 %d 页, %d 字符', len(reader.pages), len(result))
        return result
    except Exception as e:
        _logger.warning('PDF 解析失败: %s', e)
        return ''


def _from_docx(file_bytes: bytes) -> str:
    """python-docx 段落提取 Word 文本."""
    try:
        from docx import Document
    except ImportError:
        _logger.warning('python-docx 未安装, 无法解析 DOCX')
        return ''

    try:
        doc = Document(io.BytesIO(file_bytes))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        result = '\n'.join(paragraphs)
        _logger.info('DOCX 解析完成, 共 %d 段落, %d 字符', len(paragraphs), len(result))
        return result
    except Exception as e:
        _logger.warning('DOCX 解析失败: %s', e)
        return ''
