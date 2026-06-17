import sys

covers = {
    "c1": "/courses/1.png",
    "c2": "/courses/2.png",
    "c3": "/courses/3.jpg",
    "c4": "/courses/4.png",
    "c5": "/courses/5.jpg",
    "c6": "/courses/6.jpg",
    "c7": "/courses/7.png",
    "c8": "/courses/8.png",
    "c9": "/courses/9.jpg",
    "c10": "/courses/10.png",
    "c11": "/courses/11.png",
    "c12": "/courses/12.jpg",
    "c13": "/courses/13.png",
    "c14": "/courses/14.png",
    "c15": "/courses/15.png"
}

with open('seed_data.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    for cid, cover in covers.items():
        if f'"id": "{cid}"' in line:
            for j in range(i, min(i+10, len(lines))):
                if '"gradient":' in lines[j] and '"cover":' not in lines[j+1]:
                    lines[j] = lines[j].rstrip() + f'\n        "cover": "{cover}",\n'
                    break

with open('seed_data.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
