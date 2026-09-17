import optics_diagrams as od

tests = [
    {"diagram": "lens_ray_diagram", "heading": "عدسة محدبة", "diagram_spec": {"lens_type": "convex"}},
    {"diagram": "lens_ray_diagram", "heading": "عدسة مقعرة", "diagram_spec": {"lens_type": "concave"}},
    {"diagram": "prism_diagram", "heading": "قاعدة برنتس"},
    {"diagram": "refractive_error_diagram", "heading": "قصر النظر", "diagram_spec": {"error_type": "myopia"}},
    {"diagram": "refractive_error_diagram", "heading": "طول النظر", "diagram_spec": {"error_type": "hyperopia"}},
    {"diagram": "frame_measurement_diagram", "heading": "قياسات الإطار"},
    {"diagram": "pd_measurement_diagram", "heading": "المسافة بين الحدقتين"},
    {"diagram": "labeled_slide", "heading": "نقاط مهمة",
     "labels": [["النقطة الأولى", "a"], ["النقطة الثانية", "b"], ["النقطة الثالثة", "c"]]},
]
for i, t in enumerate(tests, 1):
    img = od.render_optics_diagram(t)
    if img is None:
        print(i, t["diagram"], "FAILED (None)")
    else:
        path = f"/tmp/diag_test_{i}_{t['diagram']}.png"
        img.save(path)
        print(i, t["diagram"], "OK ->", path)
