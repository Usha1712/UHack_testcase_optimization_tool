import json
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
import numpy as np

def load_config(config_path):
    with open(config_path, 'r') as file:
        config = json.load(file)
    return config

def extract_test_cases(config):
    test_cases = config.get("test_config", {})
    return test_cases

def combine_attributes(test_case):
    attributes = []
    attributes.append(json.dumps(test_case.get("resource_spec", "")))
    attributes.append(json.dumps(test_case.get("expected_fatals", "")))
    attributes.append(json.dumps(test_case.get("Metadata", "")))
    return " ".join(attributes)

def calculate_similarity(test_cases):
    test_case_keys = list(test_cases.keys())
    test_case_texts = [combine_attributes(test_cases[key]) for key in test_case_keys]

    vectorizer = TfidfVectorizer().fit_transform(test_case_texts)
    vectors = vectorizer.toarray()

    return vectors, test_case_keys

def kmeans_clustering(vectors, test_case_keys, num_clusters=4):
    kmeans = KMeans(n_clusters=num_clusters, random_state=0).fit(vectors)
    clusters = {i: [] for i in range(num_clusters)}
    for idx, label in enumerate(kmeans.labels_):
        clusters[label].append(test_case_keys[idx])
    return clusters

def measure_execution_time(groups, test_cases, execution_times):
    normal_execution_time = sum(execution_times.values())
    optimized_execution_time = 0

    for group in groups.values():
        max_time = max(execution_times[test_case] for test_case in group)
        optimized_execution_time += max_time

    return normal_execution_time, optimized_execution_time

def main(config_path):
    config = load_config(config_path)
    test_cases = extract_test_cases(config)

    execution_times = {key: test_cases[key].get('test_timeout', 0) for key in test_cases.keys()}

    vectors, test_case_keys = calculate_similarity(test_cases)
    num_clusters = 8
    clusters = kmeans_clustering(vectors, test_case_keys, num_clusters)

    print("Groups of similar test cases:")
    for cluster_id, group in clusters.items():
        print("Cluster {}: {}".format(cluster_id, ', '.join(group)))

    normal_time, optimized_time = measure_execution_time(clusters, test_cases, execution_times)

    print("Normal Execution Time: {} seconds".format(normal_time))
    print("Optimized Execution Time: {} seconds".format(optimized_time))

if __name__ == "__main__":
    config_path = '/home/rangu.ushasri/nutest-py3-tests/testcases/dr/draas/rpj_type_test_failover/config.json'
    main(config_path)