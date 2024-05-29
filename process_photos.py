import face_recognition
import os
import numpy as np
from sklearn.cluster import DBSCAN

def process_photos(photo_source, db_processor):
    """
    对一组照片进行人脸识别和聚类

    参数:
    photo_source (list): 照片来源列表，每个元素是一个包含文件路径和哈希值的元组 (photo_path, file_hash)
    db_processor (DBprocess): 数据库处理对象

    无返回值

    """
    encodings = []
    photo_paths = []
    file_hashes = []

    # 从数据库中获取已有的人脸数据
    existing_encodings = []
    existing_labels = []
    face_id_map = {}  # 用于存储已有的FaceID和标签的映射
    all_faces = db_processor.query_all_faces()
    for face in all_faces:
        existing_encodings.append(np.frombuffer(face[1], dtype=np.float64))  # face[1] 是人脸编码
        existing_labels.append(face[2])  # face[2] 是人脸标签
        face_id_map[face[2]] = face[0]  # face[0] 是 FaceID, face[2] 是 FaceLabel

    # 获取数据库中最大FaceID
    max_face_id = db_processor.get_max_face_id()
    unnamed_counter = max_face_id + 1 if max_face_id is not None else 1

    for photo_path, file_hash in photo_source:
        image_array = face_recognition.load_image_file(photo_path)
        face_encodings = face_recognition.face_encodings(image_array)
        # # 使用CNN算法进行人脸检测
        # face_locations = face_recognition.face_locations(image_array, model='cnn')
        # face_encodings = face_recognition.face_encodings(image_array, known_face_locations=face_locations)
        if len(face_encodings) > 0:
            encodings.extend(face_encodings)
            photo_paths.extend([photo_path] * len(face_encodings))
            file_hashes.extend([file_hash] * len(face_encodings))
            print(f"检测到人脸在照片 {photo_path} 中")
        else:
            print(f"未在照片 {photo_path} 中检测到人脸")

    # 合并新检测到的编码和已有的编码
    all_encodings = existing_encodings + encodings

    # 对人脸编码进行聚类
    try:
        if len(encodings) > 0:
            clustering = DBSCAN(eps=0.5, min_samples=5, metric="euclidean").fit(all_encodings)
            if hasattr(clustering, 'labels_'):  # 检查属性是否存在
                labels = clustering.labels_
                # 仅处理新检测到的编码部分
                for i, (photo_path, encoding, label, file_hash) in enumerate(
                        zip(photo_paths, encodings, labels[len(existing_encodings):], file_hashes)):
                    if label == -1:  # 噪声点（未分类的人脸）
                        face_label = f"未命名{unnamed_counter}"
                        face_id = db_processor.add_face_info(encoding.tobytes(), face_label)
                        unnamed_counter += 1
                    else:
                        face_label = existing_labels[label]  # 使用已有的标签
                        face_id = face_id_map[face_label]  # 获取对应的FaceID
                    # 转换photo_path为photo_info_id
                    photo_info = db_processor.query_photo_info_by_hash(os.path.basename(file_hash))
                    if photo_info:
                        photo_info_id = photo_info[0]
                        print(f"将人脸ID {face_id} 与照片ID {photo_info_id} 关联")
                        db_processor.link_face_to_photo(photo_info_id, face_id)
                        print(f"成功写入人脸信息: {face_label}")
                    else:
                        print(f"未找到与路径 {photo_path} 关联的照片信息")
            else:
                print("DBSCAN 聚类失败，未生成 labels_ 属性")
        else:
            print("未检测到任何人脸编码")
    except Exception as e:
        print(f"聚类过程中出现错误: {e}")