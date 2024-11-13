# distributed-chat
University group project

## Architecture

Our application is p2p style. Each node has same role.

## Communicate mechanism

We are using sockets. Most likely tcp protocol.

## User interface

The program will initially use command line.

## Way of working

Let's create github issues for the task. Let's use poetry for package managent and virtual environment.

# git cheatsheat
To add code to commit
```
git add -p
```

## Testing locally

Startup 2 peers. It will first fetch the base image for python and then build our image and finally startup the conatiners.

```
docker-compose up -d
```

Then after the containers are startup our project in the containers manually:

```
docker-compose exec peer1 bash
./main.py 123 peer2 123
```
And on another terminal run
```
docker-compose exec peer2 bash
./main.py 123 peer1 123
```

The containers mount the project directory inside them so all the changes you do will be immediately available container.
