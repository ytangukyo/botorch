#! /usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

# from unittest import mock

from typing import Callable
from unittest import mock

import torch
from botorch.acquisition.max_value_entropy_search import (
    _sample_max_value_Gumbel,
    _sample_max_value_Thompson,
    qMaxValueEntropy,
    qMultiFidelityMaxValueEntropy,
)
from botorch.models.model import Model
from botorch.posteriors import GPyTorchPosterior
from botorch.sampling.samplers import SobolQMCNormalSampler
from botorch.utils.testing import BotorchTestCase, MockPosterior
from gpytorch.distributions import MultivariateNormal
from torch import Tensor


class TestMaxValueEntropySearch(BotorchTestCase):
    def test_q_max_value_entropy(self):
        for dtype in (torch.float, torch.double):
            torch.manual_seed(7)
            mm = MESMockModel()
            with self.assertRaises(TypeError):
                qMaxValueEntropy(mm)

            train_inputs = torch.rand(10, 2, device=self.device, dtype=dtype)
            mm.train_inputs = (train_inputs,)
            candidate_set = torch.rand(1000, 2, device=self.device, dtype=dtype)

            # test error when number of outputs > 1
            with self.assertRaises(NotImplementedError):
                mm._num_outputs = 2
                qMaxValueEntropy(mm, candidate_set, num_mv_samples=10)

            # test with X_pending is None
            mm._num_outputs = 1  # mm.num_outputs
            qMVE = qMaxValueEntropy(mm, candidate_set, num_mv_samples=10)

            # test initialization
            self.assertEqual(qMVE.num_fantasies, 16)
            self.assertEqual(qMVE.num_mv_samples, 10)
            self.assertIsInstance(qMVE.sampler, SobolQMCNormalSampler)
            self.assertEqual(qMVE.sampler.sample_shape, torch.Size([128]))
            self.assertIsInstance(qMVE.fantasies_sampler, SobolQMCNormalSampler)
            self.assertEqual(qMVE.fantasies_sampler.sample_shape, torch.Size([16]))
            self.assertEqual(qMVE.use_gumbel, True)
            self.assertEqual(qMVE.posterior_max_values.shape, torch.Size([10, 1]))

            # test evaluation
            X = torch.rand(1, 2, device=self.device, dtype=dtype)
            self.assertEqual(qMVE(X).shape, torch.Size([1]))

            # test with use_gumbel = False
            qMVE = qMaxValueEntropy(
                mm, candidate_set, num_mv_samples=10, use_gumbel=False
            )
            self.assertEqual(qMVE(X).shape, torch.Size([1]))

            # test with X_pending is not None
            with mock.patch.object(
                MESMockModel, "fantasize", return_value=mm
            ) as patch_f:
                qMVE = qMaxValueEntropy(
                    mm,
                    candidate_set,
                    num_mv_samples=10,
                    X_pending=torch.rand(1, 2, device=self.device, dtype=dtype),
                )
                patch_f.assert_called_once()

    def test_q_multi_fidelity_max_value_entropy(self):
        for dtype in (torch.float, torch.double):
            torch.manual_seed(7)
            mm = MESMockModel()
            mm._num_outputs = 1  # mm.num_outputs
            train_inputs = torch.rand(10, 2, dtype=dtype)
            mm.train_inputs = (train_inputs,)
            candidate_set = torch.rand(10, 2, dtype=dtype)
            qMF_MVE = qMultiFidelityMaxValueEntropy(
                mm, candidate_set, num_mv_samples=10
            )

            # test initialization
            self.assertEqual(qMF_MVE.num_fantasies, 16)
            self.assertEqual(qMF_MVE.num_mv_samples, 10)
            self.assertIsInstance(qMF_MVE.sampler, SobolQMCNormalSampler)
            self.assertEqual(qMF_MVE.sampler.sample_shape, torch.Size([128]))
            self.assertIsInstance(qMF_MVE.fantasies_sampler, SobolQMCNormalSampler)
            self.assertEqual(qMF_MVE.fantasies_sampler.sample_shape, torch.Size([16]))
            self.assertIsInstance(qMF_MVE.expand, Callable)
            self.assertIsInstance(qMF_MVE.project, Callable)
            self.assertIsNone(qMF_MVE.X_pending)
            self.assertEqual(qMF_MVE.fidelity_dims, [-1])
            self.assertEqual(qMF_MVE.posterior_max_values.shape, torch.Size([10, 1]))

            # test evaluation
            X = torch.rand(1, 2, device=self.device, dtype=dtype)
            self.assertEqual(qMF_MVE(X).shape, torch.Size([1]))

    def test_sample_max_value_Gumbel(self):
        for dtype in (torch.float, torch.double):
            torch.manual_seed(7)
            mm = MESMockModel()
            candidate_set = torch.rand(3, 10, 2, dtype=dtype)
            samples = _sample_max_value_Gumbel(mm, candidate_set, 5)
            self.assertEqual(samples.shape, torch.Size([5, 3]))

    def test_sample_max_value_Thompson(self):
        for dtype in (torch.float, torch.double):
            torch.manual_seed(7)
            mm = MESMockModel()
            candidate_set = torch.rand(3, 10, 2, dtype=dtype)
            samples = _sample_max_value_Thompson(mm, candidate_set, 5)
            self.assertEqual(samples.shape, torch.Size([5, 3]))


class MESMockModel(Model):
    r"""Mock object that implements dummy methods and feeds through specified outputs"""

    def __init__(self) -> None:
        super(Model, self).__init__()

    def posterior(self, X: Tensor, observation_noise: bool = False) -> MockPosterior:
        m_shape = X.shape[:-1]
        r_shape = list(X.shape[:-2]) + [1, 1]
        mvn = MultivariateNormal(
            mean=torch.zeros(m_shape, dtype=X.dtype),
            covariance_matrix=torch.eye(m_shape[-1], dtype=X.dtype).repeat(r_shape),
        )
        return GPyTorchPosterior(mvn)
