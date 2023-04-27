import pygame
import torch
import random
import numpy as np

from collections import deque
from pacman import GameInstance, PLAYING_KEYS

MAX_MEMOMRY = 100_000
BATCH_SIZE = 1000
LR = 0.001

class Agent:
    def __init__(self):
        self.n_games = 0
        self.epsilon = 0 # randomness
        self.gamma = 0 # discount rate
        self.memory = deque(maxlen=MAX_MEMOMRY) # popleft()
        self.model = None   # TODO: Add model
        self.trainer = None # TODO: Add trainer
    
    def get_state(self, game):
        pac_row, pac_col = game.get_pacman_pos()
        ghosts_pos = game.get_ghosts_pos()
        up, right, down, left = game.get_surroundings()
        score = game.get_score()

        state = [
            pac_row,
            pac_col,
            up,
            right,
            down,
            left,
            score
        ]

        for pos in ghosts_pos:
            state.append(pos[0])
            state.append(pos[1])

        return np.array(state, dtype=int)

    def remember(self, state, action, reward, next_state, done):
        self.memory.append((state, action, reward, next_state, done))

    def train_long_memory(self):
        if len(self.memory) > BATCH_SIZE:
            mini_sample = random.sample(self.memory, BATCH_SIZE)
        else:
            mini_sample = self.memory

        states, actions, rewards, next_states, dones = zip(*mini_sample)
        self.trainer.train_step(states, actions, rewards, next_states, dones)

    def train_short_memory(self, state, action, reward, next_state, done):
        self.trainer.train_step(state, action, reward, next_state, done)

    def get_action(self, state):
        # random moves: tradeoff exploration / exploitation
        self.epsilon = 80 - self.n_games
        final_move = pygame.K_UP
        if random.randint(0, 200) < self.epsilon:
            move = random.randint(0, 3)
            match move:
                case 0:
                    final_move = pygame.K_UP
                case 1:
                    final_move = pygame.K_RIGHT
                case 2:
                    final_move = pygame.K_DOWN
                case 3:
                    final_move = pygame.K_LEFT
        else:
            state0 = torch.tensor(state, dtype=torch.float)
            prediction = self.model.predict(state)
            move = torch.argmax(prediction).item()
            match move:
                case 0:
                    final_move = pygame.K_UP
                case 1:
                    final_move = pygame.K_RIGHT
                case 2:
                    final_move = pygame.K_DOWN
                case 3:
                    final_move = pygame.K_LEFT
            
        return final_move

def train():
    plot_scores = []
    plot_mean_scores = []
    total_score = 0
    record = 0

    agent = Agent()
    game = GameInstance()

    while True:
        # get old state
        state_old = agent.get_state(game)

        # get move
        final_move = agent.get_action(state_old)

        # perform move and get new state
        final_move = pygame.K_RIGHT
        reward, done, score = game.update(final_move)
        state_new = agent.get_state(game)

        # train short memory
        agent.train_short_memory(state_old, final_move, reward, state_new, done)

        # remember
        agent.remember(state_old, final_move, reward, state_new, done)

        if done:
            # train long memory, plot result
            agent.n_games += 1
            agent.train_long_memory()

            if score > record:
                record = score
                # TODO: agent.model.save()
            
            print("Game", agent.n_games, "Score", score, "Record", record)

            # TODO: plot

if __name__ == "__main__":
    train()