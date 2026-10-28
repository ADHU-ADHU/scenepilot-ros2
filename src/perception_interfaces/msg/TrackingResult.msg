# header and mask.header are the original RGB acquisition header.
std_msgs/Header header
string session_id
string request_id
uint64 generation
string backend
string camera
string target
bool active
bool detected
uint32 detections
# Highest-confidence detection, not a persistent object identity.
sensor_msgs/Image mask
float32 confidence
float64 inference_ms
float64 request_ms
float64 frame_age_ms
bool frame_age_valid
bool depth_valid
float64 depth_z_m
float64 depth_range_m
float64 depth_mad_m
float64 depth_valid_fraction
float64 depth_offset_ms
geometry_msgs/PointStamped position
