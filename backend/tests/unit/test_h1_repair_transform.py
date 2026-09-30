from tools.fix_wordpress_body_h1 import transform_body_h1


def test_body_h1_repair_preserves_other_markup_and_removes_empty_heading():
    content = '<p>شروع</p><h1 data-start="1">عنوان <img src="/car.jpg" alt="خودرو"></h1><h1> </h1><p>پایان</p>'
    assert transform_body_h1(content) == '<p>شروع</p><h2 data-start="1">عنوان <img src="/car.jpg" alt="خودرو"></h2><p>پایان</p>'
