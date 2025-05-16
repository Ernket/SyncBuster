# Tool Introduction
SyncBuster is a race condition vulnerability testing tool. Users simply copy complete HTTP packets from BurpSuite and paste them into the tool to send two concurrent requests. 

# Key Features
- Concurrent HTTP Request Sending (Currently supports 2 concurrent packets)
- Protocol Selection (Toggle HTTPS; defaults to HTTP if unchecked)
- Request Delay (Delay individual requests, e.g., set "A=1" to send Request A 1 second after Request B)
- Chained Request Execution
- Enables follow-up operations using prior response data (e.g., validating exploit success)
- Auto-Substitution in chained requests: Dynamically replace values via regex matches using {{regex_result}}
- Debug Mode (Verbose logging for detailed analysis)
- Regex Quick Templates (Right-click input fields to insert common regex patterns)

# Development Environment
- OS: Windows 10
- Python: 3.11.8

# Usage
Install GUI dependencies:
```
pip install -r requirements.txt
```

Run the tool:
```
python syncbuster.py
```

# HTTP Request Format
Paste requests in the following format (recommended to copy directly from BurpSuite):
```
POST /api/login HTTP/1.1
Host: example.com
Content-Type: application/json
Cookie: session=abcd1234

{"username": "test", "password": "password"}
```

# FAQ
Q: Why does the tool report "Unsupported packet type" when copying from BurpSuite (e.g., GET vs POST mismatch)?<br>
A: Verify the protocol. Some sites enforce HTTPS redirection, which may alter request methods (e.g., HTTP POST → HTTPS GET during redirection).<br>

# Roadmap
- Expand chained request support for multiple packets and regex matches
- Allow manual packet additions and increased concurrency
