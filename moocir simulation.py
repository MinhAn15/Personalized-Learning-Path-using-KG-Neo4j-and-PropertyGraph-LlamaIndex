# -*- coding: utf-8 -*-
"""MOOCIR algorith

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1CZyzdb-ezPu7iLciEchkM0Z0fPJcmVo-
"""

# Cài đặt các thư viện cần thiết
!pip install tensorflow neo4j pandas numpy

# Import các thư viện
import tensorflow as tf
import pandas as pd
import numpy as np
from neo4j import GraphDatabase
from google.colab import userdata
import time

# Cấu hình Neo4j
NEO4J_CONFIG = {
    "url": userdata.get("NEO4J_URL"),
    "username": userdata.get("NEO4J_USER"),
    "password": userdata.get("NEO4J_PASSWORD"),
}

driver = GraphDatabase.driver(
        NEO4J_CONFIG["url"],
        auth=(NEO4J_CONFIG["username"], NEO4J_CONFIG["password"])
    )

# Hàm lấy tất cả khái niệm từ Neo4j
def get_concept_nodes(driver):
    with driver.session() as session:
        result = session.run("MATCH (n:KnowledgeNode) RETURN n.Node_ID LIMIT 50")  # Giới hạn để tối ưu
        return [record["n.Node_ID"] for record in result]

# Hàm kiểm tra tiên quyết của một khái niệm
def check_prerequisites(driver, concept_id, visited):
    with driver.session() as session:
        result = session.run(
            "MATCH (n:KnowledgeNode)-[:REQUIRES]->(pre:KnowledgeNode) "
            "WHERE n.Node_ID = $concept_id AND NOT pre.Node_ID IN $visited "
            "RETURN pre.Node_ID as pre_id",
            concept_id=concept_id, visited=list(visited)
        )
        return [record["pre_id"] for record in result]

# Hàm xây dựng ma trận kề dựa trên NEXT
def build_adjacency_matrix(driver, concepts):
    num_concepts = len(concepts)
    adjacency_matrix = tf.zeros([num_concepts, num_concepts], dtype=tf.float32)
    with driver.session() as session:
        for i, concept_i in enumerate(concepts):
            for j, concept_j in enumerate(concepts):
                if i != j:
                    result = session.run(
                        "MATCH (n1:KnowledgeNode)-[:NEXT]->(n2:KnowledgeNode) "
                        "WHERE n1.Node_ID = $id1 AND n2.Node_ID = $id2 "
                        "RETURN count(*) > 0 as connected",
                        id1=concept_i, id2=concept_j
                    )
                    if result.single()["connected"]:
                        adjacency_matrix = tf.tensor_scatter_nd_update(
                            adjacency_matrix, [[i, j]], [1.0]
                        )
    return adjacency_matrix

# Mô phỏng GCN
def gcn_simulation(features, adjacency_matrix):
    hidden = tf.matmul(adjacency_matrix, features)
    return tf.nn.relu(hidden)

# Cơ chế chú ý
def attention_mechanism(embeddings_list):
    attention_weights = tf.nn.softmax(tf.random.uniform([len(embeddings_list)]), axis=0)
    aggregated_embedding = tf.reduce_sum(
        tf.stack(embeddings_list) * tf.expand_dims(attention_weights, -1), axis=0
    )
    return aggregated_embedding

# Sinh lộ trình học tập
def moocir_learning_path(user_id, start_concept_id, driver, max_length=5):
    start_time = time.time()

    # Lấy danh sách khái niệm
    concepts = get_concept_nodes(driver)
    num_concepts = len(concepts)
    concept_ids = [concept for concept in concepts]

    # Tìm chỉ số bắt đầu
    try:
        start_index = concept_ids.index(start_concept_id)
    except ValueError:
        raise ValueError("Khái niệm bắt đầu không tồn tại.")

    # Khởi tạo đặc trưng
    features = tf.random.uniform([num_concepts, 100], dtype=tf.float32)

    # Xây dựng ma trận kề
    adjacency_matrix = build_adjacency_matrix(driver, concepts)

    # Áp dụng GCN
    embedding_gcn = gcn_simulation(features, adjacency_matrix)
    embeddings_list = [embedding_gcn, gcn_simulation(features, adjacency_matrix + 1.0)]

    # Tổng hợp biểu diễn
    user_embedding = attention_mechanism([emb[start_index] for emb in embeddings_list])
    concept_embeddings = [attention_mechanism([emb[i] for emb in embeddings_list])
                         for i in range(num_concepts)]

    # Tính điểm ưu tiên
    scores = [tf.reduce_sum(user_embedding * concept_emb).numpy()
             for concept_emb in concept_embeddings]

    # Sinh lộ trình
    learning_path = []
    visited = set()
    current_index = start_index

    while len(learning_path) < max_length:
        if current_index in visited:
            break
        current_concept = concepts[current_index]

        # Kiểm tra tiên quyết
        prereqs = check_prerequisites(driver, current_concept, visited)
        if prereqs:  # Nếu còn tiên quyết chưa hoàn thành
            next_index = concept_ids.index(prereqs[0])
            if next_index in visited:
                break
            current_index = next_index
            continue

        visited.add(current_index)
        learning_path.append(current_concept)

        # Tìm khái niệm tiếp theo
        neighbors = tf.where(adjacency_matrix[current_index] > 0).numpy().flatten()
        if len(neighbors) == 0:
            break
        next_index = max(neighbors, key=lambda i: scores[i] if i not in visited else -1)
        if next_index in visited:
            break
        current_index = next_index

    end_time = time.time()
    response_time = end_time - start_time

    # Truy vấn thuộc tính nút từ Neo4j
    path_details = []
    for i, concept_id in enumerate(learning_path):
        with driver.session() as session:
            result = session.run(
                "MATCH (n:KnowledgeNode) WHERE n.Node_ID = $concept_id "
                "RETURN n.Sanitized_Concept AS sanitized_concept, "
                "n.Definition AS definition, n.Difficulty AS difficulty, "
                "n.Time_Estimate AS time_estimate",
                concept_id=concept_id
            )
            record = result.single()
            if record:
                path_details.append({
                    "step": i + 1,
                    "node_id": concept_id,
                    "sanitized_concept": record["sanitized_concept"] or "Unknown",
                    "definition": record["definition"] or "Không có định nghĩa",
                    "difficulty": record["difficulty"] or "STANDARD",
                    "time_estimate": record["time_estimate"] or 30
                })
            else:
                path_details.append({
                    "step": i + 1,
                    "node_id": concept_id,
                    "sanitized_concept": "Unknown",
                    "definition": "Không có định nghĩa",
                    "difficulty": "STANDARD",
                    "time_estimate": 30
                })

    return path_details, response_time

# Chạy thử
user_id = input("Nhập ID người dùng (e.g., user:stu001): ")
start_concept_id = input("Nhập ID khái niệm bắt đầu (e.g., concept:data_task): ")

try:
    learning_path, response_time = moocir_learning_path(user_id, start_concept_id, driver)
    print("Lộ trình học tập đề xuất:")
    for step in learning_path:
        print(f"Bước {step['step']}: {step['sanitized_concept']} (ID: {step['node_id']})")
    print(f"Thời gian phản hồi: {response_time:.2f} giây")
except Exception as e:
    print(f"Lỗi: {str(e)}")