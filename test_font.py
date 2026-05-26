from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

try:
    pdfmetrics.registerFont(TTFont("CJK", "/usr/share/fonts/truetype/arphic/uming.ttc"))
    print("Registered CJK from uming.ttc")
except Exception as e:
    print(f"Error registering from uming.ttc: {e}")

try:
    pdfmetrics.registerFont(TTFont("CJK-Bold", "/usr/share/fonts/truetype/arphic/ukai.ttc"))
    print("Registered CJK-Bold from ukai.ttc")
except Exception as e:
    print(f"Error registering from ukai.ttc: {e}")

print("CJK font:", pdfmetrics.findFont("CJK"))
print("CJK-Bold font:", pdfmetrics.findFont("CJK-Bold"))
print("Registered font names:", pdfmetrics.getRegisteredFontNames())