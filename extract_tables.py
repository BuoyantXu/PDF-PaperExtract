import json
import os
import re

import fitz
import pandas as pd


# from collections import Counter


def find_image_path(d):
    image_path = d[0]['lines'][0]['spans'][0]['image_path']
    return image_path


def get_tables_loc(layout_json: dict) -> list[tuple[str, int, tuple]]:
    pdf_info = layout_json['pdf_info']

    layout = {page: pdf_info[page]['tables'] for page in range(len(pdf_info)) if
              pdf_info[page]['tables']}

    tables_loc = []
    for page in layout.keys():
        for table in layout[page]:
            table_body = [block for block in table['blocks'] if block['type'] == 'table_body']
            image_path = find_image_path(table_body) if table_body else ""
            if not image_path:
                break
            if not table['bbox'] or not table_body:
                continue
            tables_loc.append((image_path, page, table['bbox']))

    return tables_loc


def merge_text_blocks(words):
    words_cleaned = [((word[0], word[1], word[2], word[3]), word[4]) for word in words]

    def horizontal_distance(p1, p2):
        return min(abs(p1[0] - p2[2]), abs(p1[2] - p2[0]))

    def can_merge(block1, block2):
        # Check vertical alignment (same row)
        same_row = (abs(block1[0][1] - block2[0][1]) <= 5 or
                    abs(block1[0][3] - block2[0][3]) <= 5)

        # Check horizontal distance
        valid_distance = horizontal_distance(block1[0], block2[0]) < 4
        return same_row and valid_distance

    def merge_blocks(block1, block2):
        merged_coords = (
            min(block1[0][0], block2[0][0]),  # min x0
            min(block1[0][1], block2[0][1]),  # min y0
            max(block1[0][2], block2[0][2]),  # max x1
            max(block1[0][3], block2[0][3])  # max y1
        )
        merged_text = (block1[1] + " " + block2[1] if block1[0][0] <= block2[0][0]
                       else block2[1] + " " + block1[1])
        return (merged_coords, merged_text)

    # Sort by y-coordinate first, then x-coordinate
    words_cleaned.sort(key=lambda x: (x[0][1], x[0][0]))

    # Continue merging until no more merges are possible
    while True:
        merged = False
        i = 0
        while i < len(words_cleaned) - 1:
            j = i + 1
            while j < len(words_cleaned):
                if can_merge(words_cleaned[i], words_cleaned[j]):
                    merged_block = merge_blocks(words_cleaned[i], words_cleaned[j])
                    words_cleaned.pop(j)
                    words_cleaned[i] = merged_block
                    merged = True
                else:
                    j += 1
            i += 1

        if not merged:
            break

    return words_cleaned


def determine_rows_and_columns(words_cleaned):
    def has_vertical_overlap(block1, block2, overlap_threshold=0.75):
        y1_min, y1_max = block1[0][1], block1[0][3]
        y2_min, y2_max = block2[0][1], block2[0][3]
        overlap = min(y1_max, y2_max) - max(y1_min, y2_min)
        min_height = min(y1_max - y1_min, y2_max - y2_min)
        return overlap > min_height * overlap_threshold

    def has_horizontal_overlap(block1, block2, overlap_threshold=0.4):
        x1_min, x1_max = block1[0][0], block1[0][2]
        x2_min, x2_max = block2[0][0], block2[0][2]
        overlap = min(x1_max, x2_max) - max(x1_min, x2_min)
        min_width = min(x1_max - x1_min, x2_max - x2_min)
        return overlap > min_width * overlap_threshold

    # First get rows to identify header and data sections
    rows = []
    remaining_blocks = words_cleaned.copy()
    max_iterations = len(remaining_blocks) * 2 + 1000  # 设置最大迭代次数
    iteration_count = 0
    while remaining_blocks and iteration_count < max_iterations:
        iteration_count += 1
        current_row = [remaining_blocks.pop(0)]
        i = 0
        while i < len(remaining_blocks):
            if any(has_vertical_overlap(block, remaining_blocks[i]) for block in current_row):
                current_row.append(remaining_blocks.pop(i))
            else:
                i += 1
        rows.append(sorted(current_row, key=lambda x: x[0][0]))

    if iteration_count >= max_iterations:
        print("Warning: Row detection may be incomplete due to potential infinite loop.")

    # Extract row boundaries
    row_coords = []
    for row in rows:
        y_min = min(block[0][1] for block in row)
        row_coords.append(y_min)
    row_coords = sorted(row_coords)

    # 目前根据每行的文本块数量最大值进行分列 也可考虑众数
    row_counts = [len(row) for row in rows]
    # row_counts_dict = Counter(row_counts)
    # mode_count = row_counts_dict.most_common(1)[0][0] if row_counts_dict else 0
    max_count = max(row_counts) if row_counts else 0
    data_blocks = [cell for row in rows if len(row) == max_count for cell in row].copy()

    # Use data rows to determine initial column structure
    cols = []
    remaining_data = data_blocks.copy() if data_blocks else words_cleaned.copy()
    max_iterations = len(remaining_data) * 2 + 1000  # 设置最大迭代次数
    iteration_count = 0
    while remaining_data and iteration_count < max_iterations:
        current_col = [remaining_data.pop(0)]
        i = 0
        while i < len(remaining_data):
            if any(has_horizontal_overlap(block, remaining_data[i]) for block in current_col):
                current_col.append(remaining_data.pop(i))
            else:
                i += 1
        cols.append(sorted(current_col, key=lambda x: x[0][1]))

    if iteration_count >= max_iterations:
        print("Warning: Row detection may be incomplete due to potential infinite loop.")

    # Extract initial column boundaries
    col_coords = []
    for col in cols:
        x_min = min(block[0][0] for block in col)
        col_coords.append(x_min)
    col_coords = sorted(col_coords)

    return row_coords, col_coords


def assign_text_to_cells(words_cleaned, row_coords, col_coords):
    cells = []
    for block in words_cleaned:
        coords, text = block
        x0, y0, x1, y1 = coords
        # 中心坐标
        x_center = (x0 + x1) / 2
        y_center = (y0 + y1) / 2

        # 找到重叠程度最高的行
        row_overlaps = []
        for i, row_y in enumerate(row_coords):
            # 计算下一行的y坐标（如果存在）
            next_row_y = row_coords[i + 1] if i < len(row_coords) - 1 else row_y + 20
            # 如果文本块在当前行与下一行之间，则认为属于当前行
            if row_y <= y_center <= next_row_y:
                row_overlaps.append((i, abs(row_y - y_center)))

        # 找到重叠程度最高的列
        col_overlaps = []
        for j, col_x in enumerate(col_coords):
            # 计算下一列的x坐标（如果存在）
            next_col_x = col_coords[j + 1] if j < len(col_coords) - 1 else col_x + 50
            # 检查文本块是否与当前列重叠
            if col_x <= x_center <= next_col_x:
                col_overlaps.append((j, abs(col_x - x_center)))

        # 如果找到了匹配的行和列，选择重叠程度最高的
        if row_overlaps and col_overlaps:
            row_idx = min(row_overlaps, key=lambda x: x[1])[0]
            col_idx = min(col_overlaps, key=lambda x: x[1])[0]

            cells.append((row_idx, col_idx, x_center, text))

    cells = sorted(cells, key=lambda x: (x[0], x[1], x[2]))

    # 生成表格
    table = {}
    for cell in cells:
        row_idx, col_idx, _, text = cell
        text = text.replace("ﬁ", "fi")
        if (row_idx, col_idx) in table:
            table[(row_idx, col_idx)] += " " + text
        else:
            table[(row_idx, col_idx)] = text
    # Convert dictionary to DataFrame using unstack
    max_row = max(k[0] for k in table.keys()) + 1
    max_col = max(k[1] for k in table.keys()) + 1
    df_table = pd.DataFrame(index=range(max_row), columns=range(max_col))
    for (row, col), value in table.items():
        df_table.iloc[row, col] = value
    df_table = df_table.fillna('')

    return df_table


def create_table_from_text_blocks(words_cleaned):
    # 确定行和列的分界线
    row_coords, col_coords = determine_rows_and_columns(words_cleaned)
    # 将文本分配到对应的单元格
    df_table = assign_text_to_cells(words_cleaned, row_coords, col_coords)

    return df_table


def extract_and_adjust_words(doc, page, rect=None):
    """
    提取指定页面中的文本块，并根据页面方向调整坐标。

    参数:
        doc
        page_num (int): 要处理的页面编号（从 0 开始）。
        rect (fitz.Rect): 可选的裁剪区域。

    返回:
        list: 调整后的文本块列表，每个文本块包含调整后的坐标和文本内容。
    """
    # 打开 PDF 文件
    doc_page = doc[page]

    # 获取页面尺寸和旋转角度
    width, height = doc_page.rect.width, doc_page.rect.height
    rotation = doc_page.rotation

    # 提取文本块
    words = doc_page.get_text("words", clip=rect)

    # 定义坐标调整函数
    def adjust_coords(word, rotation, width, height):
        x0, y0, x1, y1, text, block_no, line_no, word_no = word
        if rotation == 90:
            # 顺时针旋转 90 度
            x0, y0 = height - y0, x0
            x1, y1 = height - y1, x1
        elif rotation == 180:
            # 旋转 180 度
            x0, y0 = width - x0, height - y0
            x1, y1 = width - x1, height - y1
        elif rotation == 270:
            # 逆时针旋转 90 度
            x0, y0 = y0, width - x0
            x1, y1 = y1, width - x1
        return (x0, y0, x1, y1, text, block_no, line_no, word_no)

    # 根据旋转角度调整每个文本块的坐标
    adjusted_words = [adjust_coords(word, rotation, width, height) for word in words]

    return adjusted_words


def extract_tables_from_pdf(path_paper):
    paper_title = os.path.basename(path_paper)
    path_layout = os.path.join(path_paper, "layout.json")
    path_origin = os.path.join(path_paper, "origin.pdf")
    path_content_list = os.path.join(path_paper, "content_list.json")

    os.makedirs(os.path.join(path_paper, "images"), exist_ok=True)

    with open(path_layout, "r", encoding="utf-8") as f:
        layout_json = json.load(f)
    with open(path_content_list, "r", encoding="utf-8") as f:
        content_list = json.load(f)

    tables_loc = get_tables_loc(layout_json)

    tables_list = []
    doc = fitz.open(path_origin)
    text = "".join([doc[page].get_text("text") for page in range(len(doc))])
    text_lines = text.split('\n')

    type_sig = 0
    type_sig_line = ""
    for text in text_lines:
        text = text.replace("∗", "")
        pattern = r'[ƚ†+].*?p\s*<\s*0\.1'
        matches = re.findall(pattern, text)
        if matches:
            type_sig = 1
            type_sig_line = "\n".join(matches)

    for image_filename, page, table_loc in tables_loc:
        # image_filename, page, table_loc = tables_loc[1]
        rect = fitz.Rect(*table_loc)

        try:
            content_footnote = [content for content in content_list if content['type'] == "table" and
                                content['img_path'] == "images/" + image_filename][0]
            content_footnote = content_footnote['table_footnote'][0]
        except:
            content_footnote = ""
        table_markdown = ""
        table_html = ""

        image = doc[page].get_pixmap(matrix=fitz.Matrix(3, 3), dpi=300, clip=rect)
        image_path = os.path.join(path_paper, "images", image_filename)
        image.save(image_path)

        table_finder = doc[page].find_tables(clip=rect)
        if table_finder.tables:
            df_table = table_finder.tables[0].to_pandas()
        else:
            try:
                # 提取文本块
                words = extract_and_adjust_words(doc, page, rect=rect)

                # 合并文本块
                words_cleaned = merge_text_blocks(words)
                # 生成表格
                df_table = create_table_from_text_blocks(words_cleaned)
                df_table.columns = df_table.iloc[0].values.tolist()
                # 删除第一行
                df_table = df_table.drop(index=0).reset_index(drop=True)
                table_markdown = df_table.to_markdown(index=False)
                table_html = df_table.to_html(index=False)
                #
                # # 如果某一列中80%的值都是空字符串，则删除该列
                # threshold = 0.8
                # null_ratios = (df_table == '').mean()
                # cols_to_drop = null_ratios[null_ratios >= threshold].index
                # df_table = df_table.drop(columns=cols_to_drop)
            except:
                df_table = None
        if df_table is not None and df_table.shape[0] > 1 and df_table.shape[1] > 1:
            tables_list.append({
                "title": paper_title,
                "page": page + 1,
                "table": df_table,
                "type_sig": type_sig,
                "type_sig_line": type_sig_line,
                "content_footnote": content_footnote,
                "image_path": image_path,
                "table_markdown": table_markdown,
                "table_html": table_html
            })

    return tables_list


def extract_tables():
    import pickle
    from glob import glob
    from tqdm import tqdm

    paths_paper = glob(r"tmp_files/*")

    tables = []
    error_list = []
    for path_paper in tqdm(paths_paper):
        try:
            tables.extend(extract_tables_from_pdf(path_paper))
        except Exception as e:
            error_list.append(path_paper)
            print(e)

    with open('tables.pkl', 'wb') as f:
        pickle.dump(tables, f)
    print("All tables extracted.")

    print(len(tables))


def process_single_paper(path_paper):
    try:
        return extract_tables_from_pdf(path_paper)
    except Exception as e:
        print(f"Error processing {path_paper}: {e}")
        return []


def extract_tables_mp():
    import pickle
    from glob import glob
    from tqdm import tqdm
    from multiprocessing import Pool, cpu_count

    paths_paper = glob(r"tmp_files/*")

    # Use 75% of available CPU cores
    n_cores = max(1, int(cpu_count() * 0.75))

    with Pool(processes=n_cores) as pool:
        # Use imap_unordered for better performance with progress bar
        results = list(tqdm(
            pool.imap_unordered(process_single_paper, paths_paper),
            total=len(paths_paper),
            desc="Extracting tables"
        ))

    # Flatten results list
    tables = [table for result in results for table in result]

    with open('tables.pkl', 'wb') as f:
        pickle.dump(tables, f)
    print("All tables extracted.")
    print(len(tables))


if __name__ == '__main__':
    # extract_tables()
    extract_tables_mp()

    # ########
    # # test #
    # ########
    # from glob import glob
    #
    # test_pdfs = glob(r"tmp_files/*")
    #
    # error_dict = {
    #     "fix_extract": [
    #         6,
    #         9,
    #         11,  # 纵向页面中横向表格Page 7+1 横向表格 page 8+1
    #     ],
    #     "fix_layout": [],
    #     "error": [],
    #     "no_stat": [0]
    # }
    #
    # path_paper = test_pdfs[16]
    # path_paper_pdf = os.path.join(path_paper, "origin.pdf")
    #
    # path_layout = os.path.join(path_paper, "layout.json")
    # path_origin = os.path.join(path_paper, "origin.pdf")
    # path_content_list = os.path.join(path_paper, "content_list.json")
    #
    # with open(path_layout, "r", encoding="utf-8") as f:
    #     layout_json = json.load(f)
    # with open(path_content_list, "r", encoding="utf-8") as f:
    #     content_list = json.load(f)
    #
    # tables_loc = get_tables_loc(layout_json)
    # # 在系统中打开PDF文件
    # os.startfile(path_paper_pdf)
    #
    # tables = extract_tables_from_pdf(path_paper)
    # tables = [table['table'] for table in tables if table['table'].shape[0] > 1 and table['table'].shape[1] > 1]
    #
    # i = 2
    # # 将第一行作为列名
    # tables[i].columns = tables[i].iloc[0].values.tolist()
    # # 删除第一行
    # tables[i] = tables[i].drop(index=0).reset_index(drop=True)
    # table_markdown = tables[i].to_markdown(index=False)
    # image_loc = tables_loc[i]
    # page = image_loc[1]
    # doc = fitz.open(path_origin)
    # rect = fitz.Rect(*image_loc[2])
    #
    # # 截图 dpi=300
    # image = doc[page].get_pixmap(matrix=fitz.Matrix(3, 3), dpi=300, clip=rect)
    # # 保存图像
    # image.save("table_image.png")
    #
    # print(table_markdown)
