---
incomplete: yes
title: A skeptic's first contact with kubernetes
---

I've been working on systems administration/engineering/infrastructure development for many years and
somehow I've not had to interact with kubernetes in any way.
I think this is lucky, as I've held a pretty low opinion of kubernetes all this time, without really having a solid basis for that.
It's mostly an opinion formed in a reactionary way to "a new way of doing things" and "unnecessary complexity".
I've found myself with some free time lately and decided to learn more about kubernetes, to see what all of this is about, and hopefully learn new concepts for infra mgmt.

There are a lot of tutorials covering installing and using kubernetes, along with fairly scattered/unconnected descriptions of what the underlying parts of the system do, and how.

My goal for this post is to gather the concepts that I've learned about in the order/abstractions that I find most undestandable.

a standard description of kubernetes would say something like:

kubernetes allows you to run arbitrary workloads\*, and provides you with the ability to:

- specify requirements (cpu, disk, memory, instance count, ..)
- dynamically scale instance count

but the more important part, is what it _does_ for you:

- bin packing of applications 
- "self-healing" (crashed instances get restarted)
- exposes services for DNS-based discovery

and it only _requires_ you to package your workload as a Docker image [](), which seems like a reasonable price to pay.

BUT
the way i see it, the essence of kubernetes can be attributed to two properties:

### Control loops
First, "resources" are managed by a set of [control loops](https://en.wikipedia.org/wiki/Control_loop) (named [Controllers](https://kubernetes.io/docs/concepts/architecture/controller/)).

A control loop has the objective of achieving a desired state, and it will do this by observing specific variables (via a sensor) and performing actions (via a control element).

An interesting detail is that the control element does not necessarily _directly_ affect what the sensor observes.

This description is very generic, so here are some examples:

- A workload that needs to process events from a queue
	- Desired state: empty queue
	- Sensor: depth of the queue
	- Control Element: update the number of running servers to process events (which can also go _down_ if the queue is empty)
- A workload that needs to horizontally scale to handle user load
	- Desired state: Maintain average CPU utilization below 80%
	- Sensor: CPU metrics from pods
	- Control Element: Spin up new Nodes in the Cluster
- Generic Health monitoring
	- Desired state: All Nodes are healthy
	- Sensor: Health metrics from nodes
	- Control Element: Remove Nodes from the cluster

### Services

introducing basic concepts, to later highlight things that surprised me in good, bad and still-undecided ways:

Pod:
	- a unit of work, consisting of a set of Docker images and their configuration
Node: 
	- a computer running the kubernetes node agent (kubelet). executes Pods.
cluster
	- a logical collection of `Node`s
service:
	- logical grouping of a set of pods
Namespace:
	- a logical subdivision of the `Cluster`. provides scope for names (like dns search domain)

<diagram>

these have some fundamental characteristics that everything else builds on top of:

pods:
- containers within a pod share networking & storage (same ip address, port space, local "scratch disk")
- **are not stable** -- they may get shut down & recreated somewhere else, with a different IP address.

services:
- **are stable over time** -- they will have a stable DNS record `<service-name>.<namespace>.svc.cluster.local` _and_ a stable IP address

## Controllers
statefulset, deployment

## workload mgmt

or "how, when and where things run"

You can create a Pod manually, using some yaml like this:
```yml
apiVersion: v1
kind: Pod
metadata:
  name: nginx
spec:
  containers:
  - name: nginx
    image: nginx:1.14.2
    ports:
    - containerPort: 80
```

but by doing that, you are _manually_ scheduling the execution of this pod _once_; what this means is that
if the node dies, then your pod will die with it, and not get re-scheduled anywhere else. Pod termination can also happen if there's resource pressure on the Node, via [eviction](https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/).

Instead of creating a Pod directly, you can create a [ReplicaSet]() which is a Controller, and as part of it's control loop it will ensure that the right number of replicas are running for your specified Pod at all times.

ReplicaSets solve the problem of Node failure/eviction deleting your Pod, but they are mostly immutable (you can only change the replicas count).
deployments, pods, replicasets


achieving desired state through a ReplicaSet (one-off, non-updatable) or a Deployment (continuous, updatable)

docker helped packaging any arbitrary app into a standardized unit

kube helps running arbitrary workloads with requirements (cpu disk etc).
bin packing & control loop

Deployment is the desired end state for an "application", scheduler takes care of it via control loop

storage;
- by default disk is ephemeral/not shared
volumes allow sharing
volumes can be ephemeral (deleted on pod stop) or persistent (..)



ltaer:
Namespaces separate workloads _by default_. pods can still talk to a Service in another namespace by explicitly

problem/solution:
sharing files between containers in a pod -> volumes



>> Your cluster could be changing at any point as work happens and control loops automatically fix failures. This means that, potentially, your cluster never reaches a stable state.

>> As long as the controllers for your cluster are running and able to make useful changes, it doesn't matter if the overall state is stable or not.


## networking

networking model:

- All Pods in the cluster share a _flat_, cluster-private IP space
- All Pods can (from a networking perspective) communicate with all other pods (unless specifically firewalled)
	- so, no segmenting some pods/nodes in VLANs, you would use a different cluster for that


why this model?

in my opinion, having services with **stable identities** over time (consistent DNS records & IP addresses) seem like the most important/fundamental part, as their design seems to have guided everything else
this makes sense, as applications do not need to deal with service discovery actively, as long as they use the Service address to connect, they will be highly available [EXPLAIN WTF SERVICE DOES BEFORE, NODE DYING, etc]

a service continuously evaluates which pods are still eligible/healthy, and if there's a change, it will reflect this
routing rules


pods run in private network (why, how? routing? )
https://github.com/kubernetes/design-proposals-archive/blob/main/network/networking.md
external to internal = garbage, double-bounced through generic "lb" node into correct lb node
external to internal could go via ingress
https://kubernetes.io/docs/concepts/services-networking/ingress/


services: headless (no ip) / normal
	- headless do not use service name via dns, you need to talk to the pods directly
		- querying the service name returns many A results, one per pod
		- in a statefulset, SRV answers are there only for Running/Healthy pods


on-node:
kube-proxy forwards "service" flows to "pods"
 - how, why? bc the service static while the node lives?
 	- every node has all rules for all services which dictate "incoming for service A -> outgoing to pod B"
		- even if they do not host the corresponding service
	=> all nodes route/forward traffic, all nodes have the same rules
	=> if node A holds pod P for service S, and P is rescheduled to node B,
	   then node A's kube-proxy will start forwarding traffic to B instead of localhost
	=> also each node will load-balance the request across all _target_ nodes (hosting the service)
	   
 - isn't pod identity supposed to make this static as well?
 	- pod name is stable, which has a dns record for headless service and statefulsets
		- is there a record just for the pod tho? no
	- pod IP is not stable

 - does it ever forward traffic to another node?
 	- maybe if the pod got moved, while the dns record lives?


---

why not



good ideas:
- controller
- pods as units (lower ipc cost)

very interesting ideas:
- stable identity (static ip for a service?)

bad ideas/bailed too early:
- plugins instead of implementing (networking)
- example queue-based work, no integration, needs keda
# end
my hot take: services (and their stable identity) and the control loop (with everything necessary to support them) 
are the only essential complexity; everything else is accidental

helm? terrible, complex, stringy typed (example of mode=x, value=y, keda queue example)
compatibility layer via env vars = ASS (ordering issues)

reliance on plugins (CNI)

why is there no support for some protocols with built-in controllers?
eg: observe an http endpoint for a measurement, this could be exported by queues, and we could have 
autoscaling based on queue depth supported without KEDA

what's the point with abstracting cloud?? why is there built-in support for AWS/GCS/.. in LoadBalancer?

