import face_recognition
import os
import sys
import numpy as np
from sklearn.cluster import DBSCAN
import matplotlib.pyplot as plt
from scipy.spatial.distance import pdist, squareform
import dlib

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

    # 获取当前脚本所在的目录
    if getattr(sys, 'frozen', False):
        # 如果是打包后的可执行文件
        base_path = sys._MEIPASS
    else:
        # 如果是源代码
        base_path = os.path.dirname(os.path.abspath(__file__))

    # # 生成模型文件的完整路径打包用的代码
    # landmark_model_path = os.path.join(base_path, "shape_predictor_68_face_landmarks.dat")
    # encoding_model_path = os.path.join(base_path, "dlib_face_recognition_resnet_model_v1.dat")
    # # 检查模型文件是否存在打包用的代码
    # if not os.path.exists(landmark_model_path) or not os.path.exists(encoding_model_path):
    #     print("模型文件缺失，请确保 'shape_predictor_68_face_landmarks.dat' 和 'dlib_face_recognition_resnet_model_v1.dat' 文件存在")
    #     return
    # # 加载人脸关键点检测模型打包用的代码
    # landmark_predictor = dlib.shape_predictor(landmark_model_path)
    # # 加载人脸编码模型打包用的代码
    # face_rec_model = dlib.face_recognition_model_v1(encoding_model_path)
    # # 加载人脸检测模型打包用的代码
    # face_detector = dlib.get_frontal_face_detector()

    for photo_path, file_hash in photo_source:
        image_array = face_recognition.load_image_file(photo_path)
        # # 使用dlib检测人脸位置 打包用的代码
        # face_locations = face_detector(image_array, 1)
        # # 获取每个检测到的人脸的关键点 打包用的代码
        # face_encodings = []
        # for face_location in face_locations:
        #     shape = landmark_predictor(image_array, face_location)
        #     face_encoding = np.array(face_rec_model.compute_face_descriptor(image_array, shape, num_jitters=10, model='large'))
        #     face_encodings.append(face_encoding)

        face_encodings = face_recognition.face_encodings(image_array, num_jitters=10, model='large')
        # # 使用CNN算法进行人脸检测
        #face_locations = face_recognition.face_locations(image_array, model='cnn')
        #face_encodings = face_recognition.face_encodings(image_array, known_face_locations=face_locations)
        if len(face_encodings) > 0:
            encodings.extend(face_encodings)
            photo_paths.extend([photo_path] * len(face_encodings))
            file_hashes.extend([file_hash] * len(face_encodings))
            print(f"检测到人脸在照片 {photo_path} 中")
        else:
            print(f"未在照片 {photo_path} 中检测到人脸")

    # 合并新检测到的编码和已有的编码
    all_encodings = existing_encodings + encodings

    # 计算人脸编码之间的欧氏距离
    distances = pdist(encodings, 'euclidean')
    distance_matrix = squareform(distances)
    # 设置中文字体
    plt.rcParams['font.sans-serif'] = ['SimHei']  # 指定默认字体
    plt.rcParams['axes.unicode_minus'] = False  # 解决保存图像时负号 '-' 显示为方块的问题
    # 绘制距离分布图
    plt.hist(distances, bins=50)
    plt.xlabel('距离')
    plt.ylabel('频率')
    plt.title('人脸编码距离分布')
    plt.show()

    # 对人脸编码进行聚类
    try:
        if len(encodings) > 0:
            clustering = DBSCAN(eps=0.2, min_samples=3, metric="euclidean").fit(all_encodings)
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