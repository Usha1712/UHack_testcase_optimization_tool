**Link for PPT, Documentation and Demo Video:** 
https://drive.google.com/drive/folders/1jm2baLzTCl7p-TIBZWAb1HMkS42O-oW3?usp=sharing

**Project Description:**
The release of new features requires a comprehensive testing process where all test cases from the beginning of the codebase are executed. This process is currently time-consuming, taking about a week or longer as the codebase and test suite expand. The goal of this project is to design and implement a test case optimization tool that identifies and groups similar test cases to reduce the overall number of tests that need to be executed, thereby decreasing the total execution time without compromising the quality and coverage of the tests.

**Script Description**
The script identifies similar test cases using a combination of TF-IDF vectorization and K-means clustering, which helps to group test cases that have similar attributes. The script optimizes execution time by considering only the most time-consuming test case within each cluster of similar test cases. This approach effectively reduces redundancy by ensuring that running the representative test case of each cluster suffices to cover the scenarios represented by that cluster.

**Steps in the Process**
1.	Combining Attributes:
•	The combine_attributes function gathers various attributes of each test case (e.g., resource_spec, expected_fatals, Metadata) into a single string. This string represents the test case for text vectorization.
2.	TF-IDF Vectorization:
•	The calculate_similarity function uses TfidfVectorizer from scikit-learn to convert the combined attribute strings into numerical vectors. TF-IDF (Term Frequency-Inverse Document Frequency) helps to quantify the importance of words in the context of each test case, allowing for effective similarity measurement.
3.	Cosine Similarity: Used cosine similarity to compute the similarity between test case vectors.
4.	Clustering: Applied K-means clustering on the cosine similarity matrix to group similar test cases.
This ensures that similar test cases are efficiently grouped, and only the most time-consuming test case from each cluster is executed, optimizing the overall testing process while maintaining coverage and quality.
5.	K-means Clustering:
•	The kmeans_clustering function applies K-means clustering to these vectors. This algorithm partitions the test cases into clusters based on their similarity. Test cases within the same cluster are considered similar or redundant.
6.	Execution Time Optimization:
•	The measure_execution_time function calculates the total execution time by:
•	Summing up the execution times of all test cases for the normal execution scenario.
•	Summing up the maximum execution time of test cases within each cluster for the optimized execution scenario. This step ensures that only the most time-consuming test case in each cluster is considered, thereby skipping the execution of other similar (or redundant) test cases in the cluster.

**Key Points of the script:**
•	TF-IDF Vectorization: Converts text data of test cases into numerical vectors to quantify their similarities.
•	K-means Clustering: Groups test cases into clusters based on these vectors, identifying similar or redundant test cases.
•	Execution Time Optimization: Measures the total time for running test cases, with and without optimization, by considering the maximum time for the most time-consuming test case within each cluster.

**Usage:**
python3 test_optimization.py

**Results**
![image](https://github.com/Usha1712/UHack_testcase_optimization_tool/assets/158131100/98efeb9b-75e8-425b-80e6-42e0412c52ce)
![image](https://github.com/Usha1712/UHack_testcase_optimization_tool/assets/158131100/02ac6986-a642-44b7-81d3-0f31b49e211e)
![image](https://github.com/Usha1712/UHack_testcase_optimization_tool/assets/158131100/895e6143-d182-4e4b-8945-9ee2d473f604)


