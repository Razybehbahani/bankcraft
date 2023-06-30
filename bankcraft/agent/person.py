import random
import pandas as pd
import numpy as np
from bankcraft.agent.business import Business
from bankcraft.agent.general_agent import GeneralAgent
from bankcraft.agent.merchant import Merchant
from bankcraft.transaction import *
from bankcraft.motivation import Motivation
from bankcraft.steps import steps


class Person(GeneralAgent):
    def __init__(self, model,
                 initial_money):
        super().__init__(model)
        self.money = initial_money

        self.monthly_housing_cost = np.random.normal(2000, 650)
        self.housing_cost_frequency = random.choice([steps.step['biweekly'], steps.step['month']])
        self.housing_cost_per_pay = self.monthly_housing_cost * self.housing_cost_frequency / steps.step['month']

        self.monthly_salary = self.monthly_housing_cost / 0.34  # or np.random.normal(5500, 1800)
        self.salary_frequency = random.choice([steps.step['biweekly'], steps.step['month']])
        self.salary_per_pay = self.monthly_salary * self.salary_frequency / steps.step['month']

        self.has_subscription = random.randint(0, 1)
        self.subscription_amount = self.has_subscription * random.randrange(0, 100)
        self.has_membership = random.randint(0, 1)
        self.membership_amount = self.has_membership * random.randrange(0, 100)

        self.employer = None

        self.motivation = Motivation()
        self.txn_motivation = None
        self.txn_motivation_score = 1
        self.bank_accounts = self.assign_bank_account(model, initial_money)

        self.txn_counter = 0
        self.landlord = Business(model, business_type='Landlord')
        self.payerBusiness = Business(model, business_type='test') # a temporary business for recieving scheduled transactions
        self.schedule_txn = pd.DataFrame()

    def update_motivation(self, key, amount):
        value = self.motivation.motivation_dict[key] - amount/1000
        self.motivation.motivation_dict.update({key: value})

    def reset_motivation(self):
        self.motivation = Motivation()

    def set_home(self, home):
        self.home = home

    def set_social_node(self, social_node):
        self.social_node = social_node

    def set_work(self, work):
        self.work = work

    def set_schedule_txn(self):
        txn_list = [['Type', 'Amount', 'Frequency', 'Receiver'],
                    ['Rent/Mortgage', self.housing_cost_per_pay, self.housing_cost_frequency, self.landlord],
                    ['Utilities', np.random.normal(loc=200, scale=50), steps.steps['month'], 'Utility Company'],
                    ['Memberships', self.membership_amount, steps.steps['month'], 'Business'],
                    ['Subscriptions', self.subscription_amount, steps.steps['month'], 'Business'],
                    ['Bills', random.randrange(10, 300), steps.steps['month'], 'Business']]
        self.schedule_txn = pd.DataFrame(txn_list[1:], columns=txn_list[0])

    def pay_schedule_txn(self):
        # for all types of transactions if the probability is met, and step is a multiple of frequency, do the transaction
        for index, row in self.schedule_txn.iterrows():
            if self.model.schedule.steps % row['Frequency'] == 0:
                self.pay(row['Amount'], row['Receiver'])

    def pay(self, amount, receiver):
        if type(receiver) == str:
            receiver = self.payerBusiness
        transaction = Cheque(self.bank_accounts[0][0],
                             receiver.bank_accounts[0][0],
                             amount, self.model.schedule.steps,
                             self.txn_counter)
        self.update_txn_records(receiver, amount, 'Cheque')
        transaction.do_transaction()
        self.txn_counter += 1

    def spend(self, amount, spending_prob):
        if random.random() > spending_prob:
            if self.money >= amount:
                recipient = random.choice(self.model.schedule.agents)
                transaction = Cheque(self.bank_accounts[0][0],
                                     recipient.bank_accounts[0][0],
                                     amount, self.model.schedule.steps,
                                     self.unique_id
                                     )
                self.update_txn_records(recipient, amount, "Cheque")
                transaction.do_transaction()
                self.txn_counter += 1

    def set_social_network_weights(self):
        all_agents = self.model.schedule.agents
        weight = {}
        for agent in all_agents:
            if isinstance(agent, Person):
                if agent != self:
                    weight[agent] = self.model.social_grid.edges[self.social_node, agent.social_node]['weight']
                else:
                    weight[agent] = 0
        self._social_network_weights = weight

    def lend_borrow(self, amount):
        weight = self._social_network_weights
        other_agent = random.choices(list(weight.keys()), weights=list(weight.values()), k=1)[0]
        #change the weights of the edges between the agent and the other agents
        self.adjust_social_network(other_agent)
        # borrowing from other person
        if amount > 0:
            if amount < other_agent.money:
                self.money += amount
                other_agent.money -= amount
        # lending to other person
        elif amount < 0:
            if abs(amount) < self.money:
                self.money += amount
                other_agent.money -= amount

    def adjust_social_network(self, other_agent):
        self._social_network_weights[other_agent] += 0.1
        # have weights to be between 0 and 1
        if self._social_network_weights[other_agent] > 1:
            self._social_network_weights[other_agent] = 1

    def buy(self):
        # if there is a merchant agent in this location
        if not self.model.grid.is_cell_empty(self.pos):
            # get the agent in this location
            agent = self.model.grid.get_cell_list_contents([self.pos])[0]
            # if the agent is a merchant
            if isinstance(agent, Merchant):
                # if the agent has enough money to buy
                if self.money >= agent.price:
                    self.money -= agent.price
                    agent.money += agent.price

    def move(self):
        possible_steps = self.model.grid.get_neighborhood(
            self.pos,
            moore=True,
            include_center=False)
        new_position = self.random.choice(possible_steps)
        self.model.grid.move_agent(self, new_position)

    def go_home(self):
        self.model.grid.move_agent(self, self.home)

    def go_work(self):
        self.model.grid.move_agent(self, self.work)

    def update_txn_records(self, other_agent, amount, txn_type):
        transaction_data = {
            "sender": self.unique_id,
            "receiver": other_agent.unique_id,
            "amount": amount,
            "time": self.model.schedule.time,
            "transaction_id": str(self.unique_id) + "_" + str(self.txn_counter),
            "transaction_type": txn_type,
        }
        self.model.datacollector.add_table_row("transactions", transaction_data)

    def step(self):
        self.pay_schedule_txn()
