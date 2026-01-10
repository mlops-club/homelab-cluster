Hi! I'm a self-proclaimed Kubernetes denier out here trying to run a Kubernetes cluster on my home network.

## Why the K8s avoidance up to now?

1. More than 50% of my DE job at InsideSales.com back in 2019 was babysitting an Airflow deployment on EKS that I inherited from someone who had left the company. The learning curve was a infinite black hole. Airflow constantly went down. I actually thought it was endlessly fun... for my own learning. I'd hardly recommend the same experience to a team who just wants to get workloads to happen.

2. I'd played with docker swarm and docker compose to self-host rootski.io back in 2019. It was great for self-hosting... but it was brittle enough, I learned I preferred managed tools.

3. I'd used AWS Elastic Container Service (ECS)--an abstraction that saves you from most of the learning curve of K8s, but you still get

    1. rewarded for using Docker containers and adhering to 12-factor app principles (autoscaling, rollbacks, secrets management, deployments, etc.)

    2. Premium IaC support... meaning no terraform. Yes, CloudFormation has its issues. But AWS CDK is my favorite free IaC tool, and you get things like a delete button in a UI, which

    3. less learning curve and less to manage

## Why the K8s interest now?

It's not for the usual reasons thrown around. I.e. it's not because I necessarily care about

- multi-cloud agnosticism... I feel like this turned out to be a bit of a myth even with kubernetes.

- massive scale

My personal interest in getting back into kubernetes now is:

- The MLOps ecosystem in Kubernetes has progressed massively in the last few years:
  - Kubeflow has more incubation from RedHat
  - KubeTorch by RunHouse just open sourced
  - GPU support on Kubernetes is [getting better (Medium article)](https://medium.com/@sunzoomass/how-kubernetes-evolved-to-tame-the-gpu-beast-2025-edition-3da73ecfae23)


- My whole career, I've pushed back against complexity. I'll say "wait, is Kubernetes really the best way to do this? Why not managed _____?" A common response is "you've just never seen Kubernetes done 'right'" or "your knowledge of kubernetes is out of date--it has progressed since you used it."