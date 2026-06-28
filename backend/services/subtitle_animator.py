def generate_kinetic_subtitles(words_data: list[dict], output_ass_path: str):
    header = """[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: PopStyle,Arial,80,&H0000FFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,2,0,1,4,0,5,10,10,120,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
    body = ""
    for w in words_data:
        body += f"Dialogue: 0,{w['start']},{w['end']},PopStyle,,0,0,0,,{{\\t(0,80,\\fscx115\\fscy115)}}{w['word']}\n"
    with open(output_ass_path, "w", encoding="utf-8") as f: f.write(header + body)