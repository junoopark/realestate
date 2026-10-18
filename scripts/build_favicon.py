"""브라우저 탭 아이콘(파비콘)의 PNG·ICO 판을 만든다.

원본: frontend/assets/favicon.svg (64×64 격자, 남색 바탕에 흰 집). 모양을 바꾸면 아래 도형 좌표도 함께 고친다.
출력: frontend/favicon.ico              16·32·48px  (/favicon.ico 를 직접 찾는 브라우저용)
      frontend/assets/apple-touch-icon.png  180px  (iOS 홈 화면용, 모서리는 iOS 가 둥글게 깎으므로 꽉 채운다)

처리: 8배 크기로 그린 뒤 줄여서 가장자리를 매끄럽게 한다. Pillow 가 필요하다.

사용법:
  python scripts/build_favicon.py
"""

import os

from PIL import Image, ImageDraw

ROOT = os.path.join(os.path.dirname(__file__), "..", "frontend")
NAVY = "#233a70"        # style.css 의 --masthead
WHITE = "#ffffff"
SCALE = 8               # 이 배수로 그린 뒤 줄인다

# favicon.svg 와 같은 64 격자 좌표
ROOF = [(9, 33), (32, 12), (55, 33)]
BODY = (16, 30, 48, 52)
CHIMNEY = (41, 15, 47, 27)
DOOR = (28, 39, 36, 52)


def draw(size, radius):
    big = size * SCALE
    k = big / 64
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, big - 1, big - 1), radius=radius * k, fill=NAVY)
    d.polygon([(x * k, y * k) for x, y in ROOF], fill=WHITE)
    for box, color in ((BODY, WHITE), (CHIMNEY, WHITE), (DOOR, NAVY)):
        d.rectangle([v * k for v in box], fill=color)
    return img.resize((size, size), Image.LANCZOS)


def main():
    icons = [draw(s, 14) for s in (16, 32, 48)]
    icons[-1].save(os.path.join(ROOT, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)],
                   append_images=icons[:-1])
    draw(180, 0).convert("RGB").save(os.path.join(ROOT, "assets", "apple-touch-icon.png"))
    print("favicon.ico, assets/apple-touch-icon.png 를 만들었다")


if __name__ == "__main__":
    main()
