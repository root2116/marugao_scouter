import dlib
import cv2
import os
import sys
import numpy as np
from scipy.optimize import minimize
import argparse
from shapely.geometry import Polygon
from PIL import Image
from shapely.geometry import Point
from scipy.interpolate import splprep, splev, interp1d
from face_contour import get_face_contour_points, get_head_contour_points

predictor_path = "shape_predictor_68_face_landmarks.dat"

# dlibの顔検出器と顔のランドマーク検出器を初期化
detector = dlib.get_frontal_face_detector()
predictor = dlib.shape_predictor(predictor_path)

def distance_to_circle_sum_of_squares(params, points):
        cx, cy, r = params
        distances = np.sqrt((points[:, 0] - cx) ** 2 + (points[:, 1] - cy) ** 2) - r
        return np.sum(distances ** 2)

def get_world_points(shape, image, points):
    image_points = np.array([
        (shape.part(30).x, shape.part(30).y),     # Nose tip
        (shape.part(8).x, shape.part(8).y),       # Chin
        (shape.part(36).x, shape.part(36).y),     # Left eye left corner
        (shape.part(45).x, shape.part(45).y),     # Right eye right corner
        (shape.part(48).x, shape.part(48).y),     # Left Mouth corner
        (shape.part(54).x, shape.part(54).y)      # Right mouth corner
    ], dtype="double")

    model_points = np.array([
        (0.0, 0.0, 0.0),             # Nose tip
        (0.0, -447.0, -208.0),        # Chin
        (-293.0, 230.0, -298.0),     # Left eye left corner
        (293.0, 230.0, -298.0),      # Right eye right corner
        (-150.0, -192.0, -208.0),    # Left Mouth corner
        (150.0, -192.0, -208.0)      # Right mouth corner
    ])

    focal_length = 1.0 * image.shape[1]
    center = (image.shape[1] / 2, image.shape[0] / 2)
    camera_matrix = np.array([
        [focal_length, 0, center[0]],
        [0, focal_length, center[1]],
        [0, 0, 1]
    ], dtype="double")

    dist_coeffs = np.zeros((4,1)) # 歪み係数（無視）

    success, rotation_vector, translation_vector = cv2.solvePnP(model_points, image_points, camera_matrix, dist_coeffs)

    rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
    
    print("rotation_matrix")
    print(rotation_matrix)
    print("translation_vector")
    print(translation_vector)
    
    inv_r_matrix = np.linalg.inv(rotation_matrix)

    print("inv_r_matrix")
    print(inv_r_matrix)


    z_world = -500.0

    world_coordinates = []


    print(image.shape)
    print(center[0], center[1])

    for point in points:
        
        image_point = np.array([point[0], point[1], 1.0], dtype="double")
        normalized_camera_point = np.linalg.inv(camera_matrix) @ image_point
        

        inv_r_t = inv_r_matrix @ translation_vector
        inv_r_n = inv_r_matrix @ normalized_camera_point

        scale = (z_world + inv_r_t[2]) / inv_r_n[2]

       
        camera_point = scale * normalized_camera_point
        
        world_point = inv_r_matrix @ (camera_point - translation_vector.flatten())

    
        world_coordinates.append((world_point[0], world_point[1]))
        
    
    
    normal_vector = rotation_matrix @ np.array([0, 0, 1])
    normal_vector = -normal_vector

    camera_vector = np.array([0, 0, 1])
    angle = calculate_angle_between_vectors(normal_vector, camera_vector)
    print(f"Angle: {angle}")
    return world_coordinates, rotation_matrix, translation_vector, camera_matrix, z_world, angle

def calculate_angle_between_vectors(v1, v2):
    unit_v1 = v1 / np.linalg.norm(v1)
    unit_v2 = v2 / np.linalg.norm(v2)
    dot_product = np.dot(unit_v1, unit_v2)
    angle = np.arccos(dot_product)
    return angle


def make_positive(points):
    min_x = points[0][0]
    min_y = points[0][1]

    for point in points:
        if point[0] < min_x:
            min_x = point[0]
        
        if point[1] < min_y:
            min_y = point[1]

    positive_points = []
    for point in points:
        positive_point = np.array([point[0] - min_x + 1, point[1] - min_y + 1])
        positive_points.append(positive_point)

    positive_points = np.array(positive_points)
    return positive_points, min_x, min_y

        
        
def get_outline(landmarks):
    # 外側のランドマークポイントを取得
    points = []
    for n in list(range(0, 17)):
        points.append(landmarks[n])
        # cv2.circle(image, (x, y), 2, (0, 255, 0), -1)
    
    for n in list(range(26, 16, -1)):
        
        points.append(landmarks[n])
        # cv2.circle(image, (x, y), 2, (0, 255, 0), -1)

    return points

def convert_world_to_image(r_matrix, t_vector, camera_matrix, z_point, points):
    converted_points = []
    for point in points:
        camera_point = r_matrix @ np.array([point[0], point[1], z_point]) + t_vector.flatten()
        
        normalized_camera_point = camera_point / camera_point[2]

        converted_point = camera_matrix @ normalized_camera_point

        converted_points.append(converted_point[:2])

    return converted_points

def evaluate_image_with_dlib(original_image, is_adjusted=True):
    gray = cv2.cvtColor(original_image, cv2.COLOR_BGR2GRAY)
    
    # 顔検出
    faces = detector(gray)
    shapes = [predictor(gray, face) for face in faces]
    # shapesを1番のランドマークの座標順にソート
    shapes = sorted(shapes, key=lambda x: x.part(0).x)


    evaluated_images = []
    merged_image = original_image.copy()

    scores = []
    # 顔のランドマークを描画
    for i, shape in enumerate(shapes):
        image = original_image.copy()
        original_landmarks = np.array([(p.x, p.y) for p in shape.parts()])

        if is_adjusted:
            landmarks, r_matrix, t_vector, camera_matrix, z_point, head_angle = get_world_points(shape, image, original_landmarks)
        else:
            landmarks = original_landmarks

        font_scale = min(image.shape[1], image.shape[0]) / 1000
        font_thickness = int(font_scale * 2)
        
        points = get_outline(landmarks)
        

        # すべての点を正にする
        offset_x = 0
        offset_y = 0

        if is_adjusted:
            points, offset_x, offset_y = make_positive(points)
        
        for i in range(len(points)):
            points[i] = (points[i][0].astype(np.float32), points[i][1].astype(np.float32))

        

        contour = np.array(points, np.float32)
        area = cv2.contourArea(contour)
        print(f"Polygon Area: {area}")

        points = contour
        center = np.mean(points, axis=0)

        # 顔の角度を計算
        left = (landmarks[39][0], landmarks[39][1]) # 左目頭
        right = (landmarks[42][0], landmarks[42][1]) # 右目頭

        face_angle = np.arctan2(right[1] - left[1], right[0] - left[0])
        S = []
        for point in points:
            angle = np.arctan2(point[1] - center[1], point[0] - center[0])
            if is_adjusted:
                if -np.pi  <= angle - face_angle <= 0:
                    S.append(point)
            else:
                if 0 <= angle - face_angle <= np.pi:
                    S.append(point)
        
        S = np.array(S)

        initial_guess = [center[0], center[1], np.mean(np.linalg.norm(S - center, axis=1))]
        result = minimize(distance_to_circle_sum_of_squares, initial_guess, args=(S,))
        cx, cy, r = result.x
        print(f"Fitted Circle: center=({cx}, {cy}), radius={r}")


        # 円の面積を計算
        circle_area = np.pi * r ** 2
        print(f"Circle Area: {circle_area}")

    
        circle_contour = np.array([[cx + r * np.cos(theta), cy + r * np.sin(theta)] for theta in np.linspace(0, 2 * np.pi, 100)])
        circle_contour = circle_contour.astype(np.float32)

        
        points_poly = Polygon(points)
        circle_poly = Polygon(circle_contour)

        intersection = points_poly.intersection(circle_poly)
        intersection_area = intersection.area



        
        
        
        # 多角形を描画

        
        original_points = get_outline(original_landmarks)

        original_points = np.array(original_points, np.int32)
        original_points = original_points.reshape((-1, 1, 2))
        
        cv2.polylines(image, [original_points], isClosed=True, color=(255, 0, 0), thickness=font_thickness*2)
        cv2.polylines(merged_image, [original_points], isClosed=True, color=(255, 0, 0), thickness=font_thickness*2)

        # 円を描画
        
        circle_contour = [np.array([p[0]+offset_x, p[1]+offset_y]) for p in circle_contour]


        if is_adjusted:
            circle_contour = convert_world_to_image(r_matrix, t_vector, camera_matrix, z_point, circle_contour)
            circle_center = convert_world_to_image(r_matrix, t_vector, camera_matrix, z_point, [(cx+offset_x, cy+offset_y)])
            cx = circle_center[0][0]
            cy = circle_center[0][1]
            
            circle_point = circle_contour[0]
            r = np.sqrt((circle_point[0] - cx) ** 2 + (circle_point[1] - cy) ** 2)
            


        
        marugao_score = (intersection_area / area) 
        scores.append(marugao_score)
        print(f"Marugao Score: {marugao_score}")
       
        
        circle_contour = np.array(circle_contour, np.int32)
        circle_contour = circle_contour.reshape((-1, 1, 2))
        cv2.polylines(image, [circle_contour], isClosed=True, color=(0, 0, 255), thickness=font_thickness*2)
        cv2.polylines(merged_image, [circle_contour], isClosed=True, color=(0, 0, 255), thickness=font_thickness*2)

        

        # Roundness Ratioを円の上のテキストとして描画
        text = f"Marugao: {marugao_score*100:.3f}"
        text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 2)[0]
               
        
        

       

        text_x = int(cx)
        text_y = int(cy - r - 10)
        
        # テキストが画像の右端を超えないように調整
        if text_x + text_size[0] > image.shape[1]:
            text_x = image.shape[1] - text_size[0] - 10

        # テキストが画像の上端を超えないように調整
        if text_y - text_size[1] < 0:
            text_y = text_size[1] + 10

        cv2.putText(image, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 255), font_thickness*2)
        text = f"{marugao_score*100:.3f}"
        cv2.putText(merged_image, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 255), font_thickness*2)

        evaluated_images.append(image)

    if len(evaluated_images) > 1:
        evaluated_images.append(merged_image)
    

    return evaluated_images, scores




def get_landmarks(self, image):
    img = dlib.load_rgb_image(image)
    detection = self.detector(img, 1)[0]
    face_landmarks = [np.array([item.y, item.x]) for item in self.shape_predictor(img, detection).parts()]
    return face_landmarks


def find_insertion_index(contour, end_point):
    
    # 最も離れている隣同士の点を探す
    max_distance = 0
    max_index = 0
    for i in range(len(contour)):
        distance = np.linalg.norm(contour[(i+1) % len(contour)] - contour[i])
        if distance > max_distance:
            max_distance = distance
            max_index = i

    
    
    return (max_index + 1) % len(contour)


# 最も離れた点同士が最初と最後になるように輪郭をシフト
def shift_contour(contour):
    max_distance = 0
    max_index = 0
    for i in range(len(contour)):
        distance = np.linalg.norm(contour[(i+1) % len(contour)] - contour[i])
        if distance > max_distance:
            max_distance = distance
            max_index = i

   
    return np.roll(contour, -max_index-1, axis=0)


# contourはface_angleで回転済みだとする
def ignore_protrusion(contour):
    original_contour = contour.copy()
    # contour : (N, 2)
    # 順番はそのままで、y座標が大きい値を30%だけ取得
    contour = contour[contour[:, 1] > np.percentile(contour[:, 1], 35)]

    
    
    # 10%の一定の間隔で点を取得
    filtered_contour = [contour[0]]

    interval = int(len(contour) * 0.1)
    if interval < 0:
        interval = 1

    for i in range(interval, len(contour), interval):
        filtered_contour.append(contour[i])
    
    if not np.array_equal(filtered_contour[-1], contour[-1]):
        filtered_contour.append(contour[-1])

    filtered_contour = np.array(filtered_contour)
    
    # contourを使ったスプライン補間
    tck, u = splprep([filtered_contour[:, 0], filtered_contour[:, 1]], s=0)

    # 輪郭を再サンプリング
    new_contour = np.array(splev(np.linspace(0, 1, len(original_contour)), tck)).T
    

    return new_contour





        




# 顔が含まれるように画像をクロップ
def crop_face(image, face):

    img_w = image.shape[1]
    img_h = image.shape[0]
    
    _, _, face_w, face_h = face.left(), face.top(), face.width(), face.height()

    padding = 0.5

    rect_top = int(face.top()) - (face_h * padding)
    if rect_top < 0:
        rect_top = 0

    rect_bottom = int(face.bottom()) + (face_h * padding)

    if rect_bottom > img_h:
        rect_bottom = img_h

    rect_left = int(face.left()) - (face_w * padding)

    if rect_left < 0:
        rect_left = 0

    rect_right = int(face.right()) + (face_w * padding)

    if rect_right > img_w:
        rect_right = img_w

    return image[int(rect_top):int(rect_bottom),int(rect_left):int(rect_right)], rect_top, rect_left


def get_lower_contour_points(contour, face_angle, center):
    points = []
    for point in contour:
        angle = np.arctan2(point[1] - center[1], point[0] - center[0])
        if 0 <= angle - face_angle <= np.pi:
            points.append(point)
    
    points = np.array(points)

    return points

def get_upper_contour_points(contour, face_angle, center):
    points = []
    for point in contour:
        angle = np.arctan2(point[1] - center[1], point[0] - center[0])
        if -np.pi <= angle - face_angle <= 0:
            points.append(point)
    
    points = np.array(points)

    return points


def resample_contour(points, num_points):
    # Calculate cumulative distance along the contour
    distances = np.sqrt(np.sum(np.diff(points, axis=0)**2, axis=1))
    cumulative_distances = np.insert(np.cumsum(distances), 0, 0)

    # Create an interpolator function for the cumulative distance
    fx = interp1d(cumulative_distances, points[:, 0], kind='linear')
    fy = interp1d(cumulative_distances, points[:, 1], kind='linear')

    # Generate equally spaced cumulative distances
    equal_distances = np.linspace(0, cumulative_distances[-1], num_points)

    # Generate new points
    new_points = np.vstack((fx(equal_distances), fy(equal_distances))).T
    return new_points
    

def rate_roundness(original_image):
        
    gray = cv2.cvtColor(original_image, cv2.COLOR_BGR2GRAY)
    
    # 顔検出
    faces = detector(gray)
    shapes = [predictor(gray, face) for face in faces]

    faces_shapes = list(zip(faces, shapes))

    faces_shapes = sorted(faces_shapes, key=lambda x: x[0].left())



    print(f"Number of faces: {len(faces)}")
    print(f"Image size: {original_image.shape[0]}x{original_image.shape[1]}")

    annotated_images = []
    scores = []


    for face, shape in faces_shapes:
        image = original_image.copy()


        face_image, rect_top, rect_left = crop_face(image, face)
        
        font_scale = min(face_image.shape[1], face_image.shape[0]) / 1000
        font_thickness = max(int(font_scale * 3),2)

        print("Font Scale: ", font_scale)
        print("Font Thickness: ", font_thickness)

        
        contour = get_face_contour_points(face_image)
        
        
        if not contour:
            continue


        # contour は512x512の画像に対する輪郭座標なので、オリジナル画像に対する座標に変換
        contour = np.array(contour, np.float32)
        contour[:, 0] = contour[:, 0] * face_image.shape[1] / 512
        contour[:, 1] = contour[:, 1] * face_image.shape[0] / 512


        
        area = cv2.contourArea(contour)

        center = np.mean(contour, axis=0)

        print(f"Contour Area: {area}")

        face_angle = np.arctan2(shape.part(45).y - shape.part(36).y, shape.part(45).x - shape.part(36).x)
        print(f"Face Angle: {face_angle}")


        # 全体の輪郭のうち、顔の下側にある輪郭のみを取得
        S = get_lower_contour_points(contour, face_angle, center)

        # 円をフィッティング
        initial_guess = [center[0], center[1], np.mean(np.linalg.norm(S - center, axis=1))]
        result = minimize(distance_to_circle_sum_of_squares, initial_guess, args=(S,))
        cx, cy, r = result.x

        print(f"Fitted Circle: center=({cx}, {cy}), radius={r}")

        circle_area = np.pi * r ** 2
        print(f"Circle Area: {circle_area}")

        

        
        # 円の上側にある輪郭のみを取得
        upper_contour = get_upper_contour_points(contour, face_angle, (cx, cy))
        if len(upper_contour) == 0:
            continue
        

        upper_contour = shift_contour(upper_contour)

    
        upper_right_point = upper_contour[0]
        upper_left_point = upper_contour[-1]

        # # upper_right_point描画
        # cv2.circle(image, (int(upper_right_point[0]), int(upper_right_point[1])), 2, (255, 255, 0), -1) 
        # # upper_left_point描画
        # cv2.circle(image, (int(upper_left_point[0]), int(upper_left_point[1])), 2, (0, 255, 0), -1) 

        # 円の下側にある輪郭のみを取得
        lower_contour = get_lower_contour_points(contour, face_angle, (cx, cy))
        if len(lower_contour) == 0:
            continue


        lower_contour = shift_contour(lower_contour)
        
        lower_right_point = lower_contour[-1]
        lower_left_point = lower_contour[0]

        # # lower_right_point描画
        # cv2.circle(image, (int(lower_right_point[0]), int(lower_right_point[1])), 2, (0, 255, 255), -1)
        # # lower_left_point描画
        # cv2.circle(image, (int(lower_left_point[0]), int(lower_left_point[1])), 2, (255, 0, 0), -1)



        
        upper_left_end_r = np.linalg.norm(upper_left_point - (cx, cy))
        lower_left_end_r = np.linalg.norm(lower_left_point - (cx, cy))

        left_end_r = (lower_left_end_r + upper_left_end_r) / 2
        
        upper_right_end_r = np.linalg.norm(upper_right_point - (cx, cy))
        lower_right_end_r = np.linalg.norm(lower_right_point - (cx, cy))

        right_end_r = (lower_right_end_r + upper_right_end_r) / 2
        
        
        left_end = (cx - left_end_r * np.cos(face_angle), cy - left_end_r * np.sin(face_angle))
        right_end = (cx + right_end_r * np.cos(face_angle), cy + right_end_r * np.sin(face_angle))
    

        left_end = np.array(left_end)
        right_end = np.array(right_end)

    

        # 上下の輪郭に円の直径の直線上の点を追加
        insertion_index = find_insertion_index(upper_contour, left_end)
        upper_contour = np.insert(upper_contour, insertion_index, left_end, axis=0)

        insertion_index = find_insertion_index(upper_contour, right_end)
        upper_contour = np.insert(upper_contour, insertion_index, right_end, axis=0)

        insertion_index = find_insertion_index(lower_contour, left_end)
        lower_contour = np.insert(lower_contour, insertion_index, left_end, axis=0)
        insertion_index = find_insertion_index(lower_contour, right_end)
        lower_contour = np.insert(lower_contour, insertion_index, right_end, axis=0)
        
    
        upper_contour = shift_contour(upper_contour)
        lower_contour = shift_contour(lower_contour)

        
       

        
        upper_contour = resample_contour(upper_contour, len(upper_contour))

        


        rotation_matrix = np.array([[np.cos(face_angle), -np.sin(face_angle)], [np.sin(face_angle), np.cos(face_angle)]])
        inv_rotation_matrix = np.array([[np.cos(-face_angle), -np.sin(-face_angle)], [np.sin(-face_angle), np.cos(-face_angle)]])
        upper_contour = upper_contour - np.array([cx, cy])
        upper_contour = upper_contour @ rotation_matrix

        

        upper_contour = ignore_protrusion(upper_contour)


    

        upper_contour = upper_contour @ inv_rotation_matrix
        upper_contour = upper_contour + np.array([cx, cy])


        

        # upper_contour_test = np.array(upper_contour, np.int32)
        # upper_contour_test = upper_contour_test.reshape((-1, 1, 2))
        # upper_contour_test[:, 0, 0] += int(rect_left)
        # upper_contour_test[:, 0, 1] += int(rect_top)
        # cv2.polylines(image, [upper_contour_test], isClosed=True, color=(255, 0, 0), thickness=font_thickness)
        

        # # # show
        # cv2.imshow("image", image)
        # cv2.waitKey(0)
        # cv2.destroyAllWindows()

        
        
        overlay = image.copy()


        left_end = (cx - r* np.cos(face_angle), cy - r * np.sin(face_angle))
        right_end = (cx + r * np.cos(face_angle), cy + r * np.sin(face_angle))
        left_end = np.array(left_end)
        right_end = np.array(right_end)

        # 上側のInclusion rateを計算 (円と長方形の共通部分をとることで半円を作ってる)
        upper_polygon = Polygon(upper_contour)
        circle = Point(cx, cy).buffer(r)

        left_upper_corner = (cx - r * np.cos(face_angle) + r * np.sin(face_angle), cy - r * np.sin(face_angle) - r * np.cos(face_angle))
        right_upper_corner = (cx + r * np.cos(face_angle) + r * np.sin(face_angle), cy + r * np.sin(face_angle) - r * np.cos(face_angle))

        upper_rectangle = Polygon([left_end, right_end, right_upper_corner, left_upper_corner])
        upper_circle = upper_rectangle.intersection(circle)

        if not upper_polygon.is_valid:
            upper_polygon = upper_polygon.buffer(0)
        
        upper_intersection_area = upper_polygon.intersection(upper_circle).area
        
        upper_inclusion_rate = upper_intersection_area / upper_polygon.area

        print(f"Upper inclusion rate: {upper_inclusion_rate}")

        

        # 下側のIoUを計算 (円と長方形の共通部分をとることで半円を作ってる)
        lower_polygon = Polygon(lower_contour)

        left_lower_corner = (cx - r * np.cos(face_angle) - r * np.sin(face_angle), cy - r * np.sin(face_angle) + r * np.cos(face_angle))
        right_lower_corner = (cx + r * np.cos(face_angle) - r * np.sin(face_angle), cy + r * np.sin(face_angle) + r * np.cos(face_angle))

        
        lower_rectangle = Polygon([left_end, right_end, right_lower_corner, left_lower_corner])
        lower_circle = lower_rectangle.intersection(circle)
        lower_intersection_area = lower_polygon.intersection(lower_circle).area
        lower_union_area = lower_polygon.union(lower_circle).area
        lower_iou = lower_intersection_area / lower_union_area

        print(f"Lower IoU: {lower_iou}")

        
        # IoUとInclusion rateの重み付き平均を計算
        alpha = 0.70
        marugao_score = upper_inclusion_rate * (1 - alpha) + lower_iou * alpha
       
        print(f"Marugao Score: {marugao_score}")
        
        # 図形を描画 -------------------------------------------------------------------


        upper_contour = np.array(upper_contour, np.int32)
        upper_contour = upper_contour.reshape((-1, 1, 2))
        lower_contour = np.array(lower_contour, np.int32)
        lower_contour = lower_contour.reshape((-1, 1, 2))

        print(upper_contour[-1])
        # upper_pointsとlower_pointsを補正
        upper_contour[:, 0, 0] += int(rect_left)
        upper_contour[:, 0, 1] += int(rect_top)
        lower_contour[:, 0, 0] += int(rect_left)
        lower_contour[:, 0, 1] += int(rect_top)

        # upper_contour と lower_contour を描画
       
        cv2.polylines(overlay, [upper_contour], isClosed=False, color=(0, 255, 0), thickness=font_thickness)
        cv2.polylines(overlay, [lower_contour], isClosed=False, color=(255, 0, 0), thickness=font_thickness)

    
        # 円を描画
        circle_contour = np.array([[cx + r * np.cos(theta), cy + r * np.sin(theta)] for theta in np.linspace(0, 2 * np.pi, 100)])
        circle_contour = np.array(circle_contour, np.int32)
        circle_contour = circle_contour.reshape((-1, 1, 2))

        # 円を補正
        circle_contour[:, 0, 0] += int(rect_left)
        circle_contour[:, 0, 1] += int(rect_top)
        
        cv2.polylines(overlay, [circle_contour], isClosed=True, color=(0, 0, 255), thickness=font_thickness)

        # Inclusion rateとIoUのキャプションを描画
    
        upper_inclusion_rate_text = f"{upper_inclusion_rate*100:.3f}"
        upper_inclusion_rate_text_size = cv2.getTextSize(upper_inclusion_rate_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale*2, font_thickness)[0]

        upper_inclusion_rate_text_x = int(cx + r)
        upper_inclusion_rate_text_y = int(cy - r/2)

        # クロップの分を補正
        upper_inclusion_rate_text_x += int(rect_left)
        upper_inclusion_rate_text_y += int(rect_top)

        # テキストが画像の右端を超えないように調整
        if upper_inclusion_rate_text_x + upper_inclusion_rate_text_size[0] > image.shape[1]:
            upper_inclusion_rate_text_x = image.shape[1] - upper_inclusion_rate_text_size[0] - 10
            
        # テキストが画像の上端を超えないように調整
        if upper_inclusion_rate_text_y - upper_inclusion_rate_text_size[1] < 0:
            upper_inclusion_rate_text_y = upper_inclusion_rate_text_size[1] + 10
        
        cv2.putText(image, upper_inclusion_rate_text, (upper_inclusion_rate_text_x, upper_inclusion_rate_text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale*2, (0, 255, 0), font_thickness)


        lower_iou_text = f"{lower_iou*100:.3f}"
        lower_iou_text_size = cv2.getTextSize(lower_iou_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale*2, font_thickness)[0]

        lower_iou_text_x = int(cx + r)
        lower_iou_text_y = int(cy + r/2)

        # クロップの分を補正
        lower_iou_text_x += int(rect_left)
        lower_iou_text_y += int(rect_top)

        # テキストが画像の右端を超えないように調整
        if lower_iou_text_x + lower_iou_text_size[0] > image.shape[1]:
            lower_iou_text_x = image.shape[1] - lower_iou_text_size[0] - 10
        
        # テキストが画像の上端を超えないように調整
        if lower_iou_text_y - lower_iou_text_size[1] < 0:
            lower_iou_text_y = lower_iou_text_size[1] + 10

        cv2.putText(image, lower_iou_text, (lower_iou_text_x, lower_iou_text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale*2, (255, 0, ), font_thickness)

        text = f"Marugao: {marugao_score*100:.3f}"
        text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale*2, font_thickness)[0]

        
    

        text_x = int(cx - r)
        text_y = int(cy - r - 10)

        # クロップの分を補正
        text_x += int(rect_left)
        text_y += int(rect_top)
        
        # テキストが画像の右端を超えないように調整
        if text_x + text_size[0] > image.shape[1]:
            text_x = image.shape[1] - text_size[0] - 10

        # テキストが画像の上端を超えないように調整
        if text_y - text_size[1] < 0:
            text_y = text_size[1] + 10

        
        
        cv2.putText(image, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale*2, (0, 0, 255), font_thickness)
        
    
        cv2.addWeighted(overlay, 0.3, image, 1 - 0.3, 0, image)



        annotated_images.append(image)
        scores.append((lower_iou, upper_inclusion_rate, marugao_score))

        
        

   
    return annotated_images, scores



if __name__=="__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--image", "-i", type=str, required=True, help="Path to the image file or directory")
    parser.add_argument("--dir", "-d", type=str, help="Path to the output directory")

    args = parser.parse_args()

    # ファイルパスの設定
    
    image_paths = [args.image]
    output_dir = args.dir


    # image_pathが画像かディレクトリかを判定(JPEG)
    if os.path.isdir(image_paths[0]):
        image_paths = [os.path.join(image_paths[0], file) for file in os.listdir(image_paths[0])]


    for image_path in image_paths:
        if not image_path.lower().endswith(('.jpg', '.jpeg', '.png')):
            continue
        # image = cv2.imread(image_path)

        # evaluated = evaluate_image(image)
        # image_name = os.path.basename(image_path)

        # cv2.imwrite(f"{output_dir}/output_{image_name}", evaluated)
        print(image_path)
        image = cv2.imread(image_path)
        processed_image, scores = rate_roundness(image)

        for i, image in enumerate(processed_image):
            
            # save the image
            image_name = os.path.basename(image_path)
            cv2.imwrite(f"{output_dir}/output_{image_name}_{i}.png", image)



        



    
