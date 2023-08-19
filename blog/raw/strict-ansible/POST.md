---
title: "strict mode" Ansible
date: 2023-08-19
tags: ansible, testing, python
description: Applying software-engineering practices to our IaC 
---

I use Ansible quite a bit for infrastructure automation, both at home and at work. Ansible's main strength is how rich its built-in modules library is.

I find _everything else_ about Ansible bad; to list a few examples:

* The inventory must gather all details from every host, regardless of running Ansible with `--limit`
* The YAML DSL hits its limits pretty quickly when going beyond simple tasks
* Tooling to deal with Ansible playbooks is extremely limited:
  * Linters detect very few statically-detectable errors, such as undefined variables
  * Testing of playbooks is not really supported at a language level


In my experience, I've found that Ansible does not help you in managing any kind of complexity, such as branching.

If complex code is hard to write correctly, the next best thing is to exercise the code and write expectation tests for it, but this is not supported by Ansible.

There's a project, [ansible-molecule](https://ansible.readthedocs.io/projects/molecule/), but I feel like it is insanity. Ansible's DSL is unable to deal with complexity, yet you are expected to validate the outcome of hundreds of steps _by writing more yaml_.


What's worked for us was to **avoid all complex logic in YAML** and I mean _all_.

We achieved this by working mainly on two topics:

- Define all variables via inventory
- Forcing all usage of variables in YAML to come from our inventory via `ansible-lint`
- Disabling logic in YAML via `ansible-lint`

### Defining all variables in the inventory

Ansible prides itself in being idempotent and declarative, yet most code written in Ansible reads the state of the target and takes decisions based on that state.
Yes, that _is_ idempotent but it goes against the philosophy of being declarative.

What we've done is to embrace the declarative nature by declaring all of our _intended state_ upfront, in the inventory for each host.

A host may end up looking like:

```yaml
arrays:
  - name: rootfs
    sizes: [800, 800]
	raid_level: 1
users:
  - name: user1
    groups: [..]
yum_repos:
  - repo1
...
```


### Forcing all variables to come from our inventory

We have an [ansible-lint](https://ansible-lint.readthedocs.io/) custom rule which only allows us to use `inventory.X` for `when` clauses.

This example does not pass linting:

```yaml
ansible.builtin.copy:
  src: example
  dest: example
when: ansible_eth1.active
```

We would instead decide during our inventory whether we should be copying this file, and writing:

```yaml
ansible.builtin.copy:
  src: example
  dest: example
when: inventory.should_copy_example_file
```

### Disabling all complex logic in YAML

We disabled _all_ complex logic in YAML statements. We don't do `and`, `not`, filters, etc.

This would fail

```yaml
systemd:
  service: vmware_agent
  enabled: inventory.system_vendor != 'VMWare'
```

Instead, we would write

```yaml
systemd:
  service: vmware_agent
  enabled: inventory.should_have_vmware_agent
```

which also prevents the use of "indirect" logic.

Removing filters is also interesting, as neither `variable|default(true)` nor `variable is defined` are kinds of patterns we would use.


## Implementing complex logic

We implement all complex logic as Ansible plugins, which are written in Python and fully unit-tested.

This lets us handle the essentialy complexity of the task without also incurring in emergent complexity from dealing with Ansible's DSL.

## Result

When you can't write complex logic in YAML, you can leverage the strength of existing Ansible modules, while dramatically reducing risk and tech debt.

We cannot write the following:

```yaml
- ansible.builtin.stat:
    path: x
  register: st

- ansible.builtin.fail:
    msg: "File not owned by root"
  when: st.stat.pw_name != 'root'
```

Instead, we'd write a module and use it as:

```yaml
- assert_ownership:
    path: x
	owner: root
```

## Integration testing

Even when having all modules unit-tested, we need to validate that assumptions made by each task are being upheld by the execution of the previous tasks.

We do this by running our playbooks against a Docker instance, similar to `ansible-molecule`'s Docker driver, but instead of asserting our desired end-state via YAML insanity, we use [testinfra](https://testinfra.readthedocs.io/en/latest/#), which lines up very nicely with our philosophy
