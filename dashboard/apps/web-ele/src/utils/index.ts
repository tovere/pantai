/**
 * @description 赋值函数
 * @param {parent} 父级对象
 * @param {child} 子级对象
 * @param {config} 配置项
 * @returns {Obj} 赋值后的对象
 */
export function assignParentValuesToChild(parent, child, config = {}) {
  for (const key in child) {
    // 检查子级对象是否包含该属性
    if (child.hasOwnProperty(key)) {
      // 如果父级对象包含对应键名或者根据配置项进行映射
      const parentKey = config[key] || key;
      if (parent.hasOwnProperty(parentKey)) {
        child[key] = parent[parentKey];
      }
    }
  }
  return child;
}
