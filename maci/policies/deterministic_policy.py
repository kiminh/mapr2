
from maci.environments.env_spec import MAEnvSpec

import tensorflow as tf

from rllab.core.serializable import Serializable

from maci.misc.nn import feedforward_net

from .nn_policy import NNPolicy

import numpy as np



class DeterministicNNPolicy(NNPolicy, Serializable):
    """Deterministic neural network policy."""

    def __init__(self,
                 env_spec=None,
                 observation_space=None,
                 action_space=None,
                 hidden_layer_sizes=(100, 100),
                 squash=False,
                 squash_func=tf.tanh,
                 name='policy',
                 noise_level=0.0,
                 u_range=1.,
                 shift=None,
                 scale=None,
                 joint=False, opponent_policy=False, agent_id=None, mu=0, theta=0.15, sigma=0.3):
        Serializable.quick_init(self, locals())
        if env_spec is None:
            self._observation_dim = observation_space.flat_dim
            self._action_dim = action_space.flat_dim
        elif isinstance(env_spec, MAEnvSpec):
            assert agent_id is not None
            self._observation_dim = env_spec.observation_space[agent_id].flat_dim
            if joint:
                self._action_dim = env_spec.action_space.flat_dim
                if opponent_policy:
                    self._action_dim = env_spec.action_space.opponent_flat_dim(agent_id)
            else:
                self._action_dim = env_spec.action_space[agent_id].flat_dim
        else:
            self._action_dim = env_spec.action_space.flat_dim
            self._observation_dim = env_spec.observation_space.flat_dim
        self._layer_sizes = list(hidden_layer_sizes) + [self._action_dim]
        self._squash = squash
        self._squash_func = squash_func
        self.agent_id = agent_id
        self._u_range = u_range
        self.shift = shift
        self.scale = scale
        self._name = name + '_agent_{}'.format(agent_id)
        self.noise_level = noise_level

        self.mu = mu
        self.theta = theta
        self.sigma = sigma
        self.state = np.ones(self._action_dim) * self.mu

        self._observation_ph = tf.placeholder(
            tf.float32,
            shape=[None, self._observation_dim],
            name='observation_agent_{}'.format(agent_id))

        self._actions = self.actions_for(self._observation_ph)

        super(DeterministicNNPolicy, self).__init__(
            env_spec, self._observation_ph, self._actions, self._name)

    def evolve_noise_state(self):
        x = self.state
        dx = self.theta * (self.mu - x) + self.sigma * np.random.randn(len(x))
        self.state = x + dx
        return self.state

    def reset_noise(self):
        self.state = np.ones(self._action_dim) * self.mu

    def set_noise_level(self, noise_level):
        # print(noise_level)
        assert (noise_level >= 0) and (noise_level <= 1)
        self.noise_level = noise_level

    def get_action(self, observation):
        return self.get_actions(observation[None])[0], None

    def get_actions(self, observations):
        feeds = {self._observation_ph: observations}
        actions = tf.get_default_session().run(self._action, feeds)
        return np.clip(actions + self._u_range * self.noise_level * self.evolve_noise_state(), -self._u_range, self._u_range)

    def actions_for(self, observations, reuse=False):

        with tf.variable_scope(self._name, reuse=reuse):
            raw_actions = feedforward_net(
                (observations,),
                layer_sizes=self._layer_sizes,
                activation_fn=tf.nn.relu,
                output_nonlinearity=None)

        if (self.shift is not None) and (self.scale is not None) and self._squash:
            tf.scalar_mul(self.scale, self._squash_func(raw_actions) + self.shift)

        return tf.scalar_mul(self._u_range, self._squash_func(raw_actions)) if self._squash else tf.clip_by_value(raw_actions, -self._u_range, self._u_range)