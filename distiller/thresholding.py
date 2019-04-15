#
# Copyright (c) 2018 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""
怎么来做weights的thresholding，这个就是pruning的核心！！

Tensor thresholding.

The code below supports fine-grained tensor thresholding and group-wise thresholding.
"""
import torch


# 直接o比较weights和threshold的大小
def threshold_mask(weights, threshold):
    """Create a threshold mask for the provided parameter tensor using
    magnitude thresholding.

    Arguments:
        weights: a parameter tensor which should be pruned.
        threshold: the pruning threshold.
    Returns:
        prune_mask: The pruning mask.
    """
    return torch.gt(torch.abs(weights), threshold).type(weights.type())


# group pruning的类
class GroupThresholdMixin(object):
    """A mixin class to add group thresholding capabilities

    TODO: this does not need to be a mixin - it should be made a simple function.  We keep this until we refactor
    """
    def group_threshold_mask(self, param, group_type, threshold, threshold_criteria):
        return group_threshold_mask(param, group_type, threshold, threshold_criteria)


# group pruning的类的主要方法们
def group_threshold_binary_map(param, group_type, threshold, threshold_criteria):
    """
    在方法threshold_policy中已经有了怎么根据weights生成mask
    这里其实是包装threshold_policy给param做一些预处理，从而可以完成直接输入param
    
    Return a threshold mask for the provided parameter and group type.

    Args:
        param: The parameter to mask
        group_type: The elements grouping type (structure).
          One of:2D, 3D, 4D, Channels, Row, Cols
        threshold: The threshold
        threshold_criteria: The thresholding criteria.
          'Mean_Abs' thresholds the entire element group using the mean of the
          absolute values of the tensor elements.
          'Max' thresholds the entire group using the magnitude of the largest
          element in the group.
    """
    # weights的维度就是3 * 3 * 32 * 64， height * width * in_chan * out_chan 所以是四维
    if group_type == '2D':
        assert param.dim() == 4, "This thresholding is only supported for 4D weights"
        view_2d = param.view(-1, param.size(2) * param.size(3))
        # 1. Determine if the kernel "value" is below the threshold, by creating a 1D
        #    thresholds tensor with length = #IFMs * # OFMs 
        #    对每一个2D位置做一个prune对应的所有channel都会被删除
        thresholds = torch.Tensor([threshold] * param.size(0) * param.size(1)).to(param.device)
        # 2. Create a binary thresholds mask, where we use the mean of the abs values of the
        #    elements in each channel as the threshold filter.
        # 3. Apply the threshold filter
        #    生成mask 过程中，所有的 policy 会reduce dim=1 与 threshold 对比
        binary_map = threshold_policy(view_2d, thresholds, threshold_criteria)
        return binary_map
    
    elif group_type == 'Rows':
        assert param.dim() == 2, "This regularization is only supported for 2D weights"
        thresholds = torch.Tensor([threshold] * param.size(0)).to(param.device)
        binary_map = threshold_policy(param, thresholds, threshold_criteria)
        return binary_map

    elif group_type == 'Cols':
        assert param.dim() == 2, "This regularization is only supported for 2D weights"
        thresholds = torch.Tensor([threshold] * param.size(1)).to(param.device)
        binary_map = threshold_policy(param, thresholds, threshold_criteria, dim=0)
        return binary_map

    elif group_type == '3D' or group_type == 'Filters':
        assert param.dim() == 4, "This thresholding is only supported for 4D weights"
        view_filters = param.view(param.size(0), -1)
        thresholds = torch.Tensor([threshold] * param.size(0)).to(param.device)
        binary_map = threshold_policy(view_filters, thresholds, threshold_criteria)
        return binary_map

    elif group_type == '4D':
        assert param.dim() == 4, "This thresholding is only supported for 4D weights"
        if threshold_criteria == 'Mean_Abs':
            if param.data.abs().mean() > threshold:
                return None
            return torch.zeros_like(param.data)
        elif threshold_criteria == 'Max':
            if param.data.abs().max() > threshold:
                return None
            return torch.zeros_like(param.data)
        exit("Invalid threshold_criteria {}".format(threshold_criteria))

    elif group_type == 'Channels':
        assert param.dim() == 4, "This thresholding is only supported for 4D weights"
        num_filters = param.size(0)
        num_kernels_per_filter = param.size(1)

        view_2d = param.view(-1, param.size(2) * param.size(3))
        # Next, compute the sum of the squares (of the elements in each row/kernel)
        kernel_means = view_2d.abs().mean(dim=1)
        k_means_mat = kernel_means.view(num_filters, num_kernels_per_filter).t()
        thresholds = torch.Tensor([threshold] * num_kernels_per_filter).to(param.device)
        binary_map = k_means_mat.data.mean(dim=1).gt(thresholds).type(param.type())
        return binary_map


def group_threshold_mask(param, group_type, threshold, threshold_criteria, binary_map=None):
    """Return a threshold mask for the provided parameter and group type.

    Args:
        param: The parameter to mask
        group_type: The elements grouping type (structure).
          One of:2D, 3D, 4D, Channels, Row, Cols
        threshold: The threshold
        threshold_criteria: The thresholding criteria.
          'Mean_Abs' thresholds the entire element group using the mean of the
          absolute values of the tensor elements.
          'Max' thresholds the entire group using the magnitude of the largest
          element in the group.
    """
    if group_type == '2D':
        if binary_map is None:
            binary_map = group_threshold_binary_map(param, group_type, threshold, threshold_criteria)

        # 3. Finally, expand the thresholds and view as a 4D tensor
        a = binary_map.expand(param.size(2) * param.size(3),
                              param.size(0) * param.size(1)).t()
        return a.view(param.size(0), param.size(1), param.size(2), param.size(3))

    elif group_type == 'Rows':
        if binary_map is None:
            binary_map = group_threshold_binary_map(param, group_type, threshold, threshold_criteria)
        return binary_map.expand(param.size(1), param.size(0)).t()

    elif group_type == 'Cols':
        if binary_map is None:
            binary_map = group_threshold_binary_map(param, group_type, threshold, threshold_criteria)
        return binary_map.expand(param.size(0), param.size(1))

    elif group_type == '3D' or group_type == 'Filters':
        if binary_map is None:
            binary_map = group_threshold_binary_map(param, group_type, threshold, threshold_criteria)
        a = binary_map.expand(param.size(1) * param.size(2) * param.size(3), param.size(0)).t()
        return a.view(param.size(0), param.size(1), param.size(2), param.size(3)), binary_map

    elif group_type == '4D':
        assert param.dim() == 4, "This thresholding is only supported for 4D weights"
        if threshold_criteria == 'Mean_Abs':
            if param.data.abs().mean() > threshold:
                return None
            return torch.zeros_like(param.data)
        elif threshold_criteria == 'Max':
            if param.data.abs().max() > threshold:
                return None
            return torch.zeros_like(param.data)
        exit("Invalid threshold_criteria {}".format(threshold_criteria))

    elif group_type == 'Channels':
        if binary_map is None:
            binary_map = group_threshold_binary_map(param, group_type, threshold, threshold_criteria)
        num_filters = param.size(0)
        num_kernels_per_filter = param.size(1)

        # Now let's expand back up to a 4D mask
        a = binary_map.expand(num_filters, num_kernels_per_filter)
        c = a.unsqueeze(-1)
        d = c.expand(num_filters, num_kernels_per_filter, param.size(2) * param.size(3)).contiguous()
        return d.view(param.size(0), param.size(1), param.size(2), param.size(3))


# 就是生成mask，通过对比weights policy和threshold的大小来生成mask
def threshold_policy(weights, thresholds, threshold_criteria, dim=1):
    """
    """
    if threshold_criteria == 'Mean_Abs':
        return weights.data.abs().mean(dim=dim).gt(thresholds).type(weights.type())
    elif threshold_criteria == 'L1':
        return weights.data.norm(p=1, dim=dim).gt(thresholds).type(weights.type())
    elif threshold_criteria == 'Max':
        maxv, _ = weights.data.abs().max(dim=dim)
        return maxv.gt(thresholds).type(weights.type())
    exit("Invalid threshold_criteria {}".format(threshold_criteria))
