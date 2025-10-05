from xml.etree.ElementTree import ElementTree
from io import BytesIO

def xml_to_bytes(root_el):
    mem = BytesIO()
    ElementTree(root_el).write(mem, encoding='utf-8', xml_declaration=True)
    mem.seek(0)
    return mem.getvalue()
