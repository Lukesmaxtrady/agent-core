# agent/deploy_tools.py
import os
import subprocess
from termcolor import cprint

def write_dockerfile(project_dir, python_version="3.10"):
    dockerfile = f"""
FROM python:{python_version}-slim
WORKDIR /app
COPY . /app
RUN pip install --upgrade pip && pip install -r requirements.txt
CMD ["python", "main.py"]
"""
    with open(os.path.join(project_dir, "Dockerfile"), "w") as f:
        f.write(dockerfile.strip())

def build_and_run_docker(project_dir):
    tag = os.path.basename(project_dir).lower()
    cprint(f"Building Docker image '{tag}:latest'...", "cyan")
    subprocess.run(["docker", "build", "-t", tag, project_dir], check=True)
    cprint(f"Running Docker container '{tag}'...", "cyan")
    subprocess.run(["docker", "run", "--rm", "-it", tag], check=True)

def write_k8s_yaml(project_dir, app_name):
    k8s_yaml = f"""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {app_name}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {app_name}
  template:
    metadata:
      labels:
        app: {app_name}
    spec:
      containers:
      - name: {app_name}
        image: {app_name}:latest
        ports:
        - containerPort: 80
"""
    with open(os.path.join(project_dir, "k8s-deploy.yaml"), "w") as f:
        f.write(k8s_yaml.strip())

def apply_k8s(project_dir):
    yaml_file = os.path.join(project_dir, "k8s-deploy.yaml")
    cprint(f"Applying Kubernetes deployment from {yaml_file}...", "cyan")
    subprocess.run(["kubectl", "apply", "-f", yaml_file], check=True)
