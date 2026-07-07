/**
 * Mock 入口文件
 * 统一导入所有 mock 模块
 */

import Mock from 'mockjs';

// 配置 Mock
Mock.setup({
  timeout: '200-600', // 模拟网络延迟 200-600ms
});

// 导入所有 mock 模块
// import './common';

console.log('[Mock] Mock 服务已启动');

export default Mock;
