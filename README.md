# distributed-chat
University group project

## Architecture

Our application is p2p style. Each node has same role.

## Communicate mechanism

We are using sockets. Most likely tcp protocol.

## User interface

The program will use just command line.

## Way of working

Let's create github issues for each task and open pr's that somebody else reviews and merges. Let's use poetry for package managent and virtual environment.

# Testing locally

Start two peers. The project's docker-compose config will first fetch the base image for python and then build our image and finally start the conatiners.

```
docker-compose up -d
```

After the containers are running, startup our project in the containers manually:

```
docker-compose exec peer1 bash
./main.py 123 peer2 123
```
And on another terminal run
```
docker-compose exec peer2 bash
./main.py 123 peer1 123
```

The containers mount the project directory inside them so all the changes you do will be immediately available containers. You just need to restart the main python script file.

## git cheatsheat
To add code to commit
```
git add -p
```
