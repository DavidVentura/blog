This is the story of how I managed to trash my server, all my VMs and 2 databases while upgrading proxmox during a
boring Sunday afternoon.  

# Upgrading the host
A few weeks ago Proxmox 6.0 was released and I decided to upgrade; this included a stretch -> buster upgrade.  
I was quite confident that the changes were going to be successful as I have upgrade this installation all the way since Wheezy.. oh wow, it's been a long time.  

The upgrade didn't go quite right, as the kernel would silently hang without any notice after a reboot. Trying to boot
previous kernels didn't help, and after 2 days fighting in a chroot I opted to simply reinstall the system without
taking any precautions; I was confident on my backups.  

# The mistake

Turns out that, while the data itself was safe, proxmox's configuration lives on an *in-memory* filesystem, mounted on `/etc/pve`
 and my backup script calls `rsync` with `-x` (`--one-file-system`).  

The files that live within `/etc/pve` are purely metadata about the containers, like what storage is used, number of
cores, memory size, **vlan**, and mounts.

While losing this metadata was quite annoying, it was not the end of the world, as all of the containers were created with some
ansible playbooks a few years ago:

```
commit ab5015c7cd11a31c7a7159a0384c627962ff6439
Author: David
Date:   Sun Dec 18 20:53:07 2016 -0300

    init dns container
```

## A small upside?
For now, to avoid this from happening again I've added `/etc/pve` to the list of filesystems to back up, and moved the
creation of VM/containers to ansible as well, an example snippet:

```yaml
- hostname: web
  disk_size: 8
  cores: 4
  memory: 2048
  interfaces:
    - name: eth0
      gw: 192.168.20.1
      ip: 192.168.20.114/24
      bridge: vmbr20
  mounts: '{"mp0":"/storage/ownclouddata,mp=/ownclouddata"}'
```

Having metadata in a static representation has the (unintended) side effect that doing static-analysis is also easier.

Re-creating the VMs is then a simple call the the `proxmox` module in ansible in a loop:

```yaml
- name: create
  proxmox:
    node: "bigserver"
    api_user: "{{ api_user }}"
    api_password: "{{ api_password }}"
    hostname: "{{ item.hostname }}"
    storage: "storage"
    cpus: "1" # numa nodes
    pubkey: "{{ pubkey }}"
    ostemplate: "{{ item.template | default(_template) }}"
    unprivileged: "{{ item.unprivileged | default('yes') }}"
    cores: "{{ item.cores | default(1)}}"
    memory: "{{ item.memory | default(2048) }}"
    onboot: "{{ item.onboot | default(1) }}"
    disk: "{{ item.disk_size | default(3) }}"
    netif: "{{lookup('proxmox_interface_format', item.interfaces)}}"
    state: present
  tags: [lxc_setup]
  loop: '{{vms}}'
```


# Restoring data

Once the VMs were re-created, I had to recover data from a few stateful containers. All of the data was accessible from
the host, as the filesystems are ZFS subvolumes and they remained intact.

## InfluxDB

Restoring influx data was quite easy:

* install influx
* stop influx
* overwrite /var/lib/influxdb/{data,wal}
* run restore command
* start influx

The restore command was:

```
root@db:~# sudo -u influxdb influx_inspect buildtsi -datadir /var/lib/influxdb/data/ -waldir /var/lib/influxdb/wal/
```

## Gogs

Restoring Gogs was also quite trivial, had to only restore files: 

* sqlite database 
* gogs daemon config
* repositories

## MySQL

Restoring MySQL was a disaster.. by this point it was well past midnight and I made a grave mistake.. Copied the
brand-new (empty) metadata files over the original metadata files, making the problem much worse.  

With [information](https://stackoverflow.com/questions/484750/restoring-mysql-database-from-physical-files) from
[multiple](https://www.nullalo.com/en/recover-mysql-innodb-tables-without-ibdata1-file/)
[sources](https://dba.stackexchange.com/questions/57120/recover-mysql-database-from-data-folder-without-ibdata1-from-ibd-files) 
I managed to re-generate the `frm` files.

To re-generate the metadata (frm files) I ran the following commands (as taken from history).  


```bash
 # make a local copy the data to work on
 2005  scp -r root@bigserver:/tank/proxmox-images/subvol-105-disk-1/var/lib/mysql/owncloud/ .
 # to run mysqlfrm you need to have the mysql binaries installed locally
 2013  sudo apt install mysql-client mysqld
 # run a test to see the output
 2021  mysqlfrm --server=root:root@db owncloud:oc_accounts.frm --port=3307
 # this looks fine; simply outputs the `CREATE TABLE` commands

 # generate table schema for all tables
 2029  for f in *.frm; do mysqlfrm --server=root:root@db owncloud:"$f" --port=3308 >> results.sql; echo $f; done
 # 2 tables failed randomly -- re running the command fixed it
 2031  mysqlfrm --server=root:root@db owncloud:oc_properties.frm --port=3308 >> results.sql 
 2032  mysqlfrm --server=root:root@db owncloud:oc_retention.frm --port=3308 >> results.sql 
 # To make this valid SQL I had a few missing ;
 2033  sed 's/COMPRESSED$/COMPRESSED;/' results.sql > rr.sql
 # Import the sql file to create the tables
 2036  mysql -u root -proot -h db owncloud < rr.sql
 # Discard the newly created tablespaces with data
 2042  for f in *.frm; do echo $f; fname=$(echo $f | cut -d. -f1); mysql -u root -proot -h db owncloud -e "alter table owncloud.$fname DISCARD TABLESPACE;"; done
 # Overwrite the data
 2043  for f in *.ibd; do scp $f root@db:/var/lib/mysql/owncloud/$f; done
 # Re-import the tablespaces
 2044  for f in *.frm; do echo $f; fname=$(echo $f | cut -d. -f1); mysql -u root -proot -h db owncloud -e "alter table owncloud.$fname IMPORT TABLESPACE;"; done
```

This got the database back in working order.. it was quite stressful though.

## Miscellaneous

For the rest of the VMs (music, web servers, reverse proxies, etc) it was just a matter of re-running the ansible
playbooks against them.  
It worked quite well; there were some differences that I had overcome with the change of the
base image between jessie and buster.


# Lessons

Backups are not backups until tested. This showed that while the data I have is kind-of safe; the cost of drives dying
(and thus losing all metadata as well) would be quite high. I intend to re-visit the backup mechanism in the near
future:

* Backup /etc/pve
* Full mysql backup
* Full influxdb backup
* Full postgres backup


I will see if it makes sense to try out some semi-automated environment recoveries somehow.
