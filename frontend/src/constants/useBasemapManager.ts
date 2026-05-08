/**
 * 底图管理常量配置
 *
 * 约定：在线底图只注册已经明确允许使用的服务。
 * 当前保留高德和天地图；后续新增底图时，只需要扩展
 * BASEMAP_LAYER_DEFINITIONS 和 BASEMAP_PRESETS 两个注册表。
 */
import XYZ from 'ol/source/XYZ';
import type { TileSourceLike } from '../composables/useTileSourceFactory';
import { prioritizeTileSourceRequest } from '../composables/useTileSourceFactory';

export const TILE_HOSTS = {
    tianditu: 't0.tianditu.gov.cn'
} as const;

export type LayerCategory = 'base' | 'label' | 'imagery' | 'vector';
export type LayerGroup = '影像' | '矢量' | '注记';

type TileSourceInstance = TileSourceLike | null;

type LayerFactoryContext = {
    tiandituTk: string;
};

type LayerSourceDefinition = {
    id: string;
    name: string;
    category: LayerCategory;
    group: LayerGroup;
    createSource: (ctx: LayerFactoryContext) => TileSourceInstance;
};

type BasemapPresetDefinition = {
    id: string;
    label: string;
    /** 从下到上的图层顺序。 */
    stack: string[];
    /** 鹰眼视图使用的图层顺序；默认复用 stack。 */
    overviewStack?: string[];
};

export const DEFAULT_BASEMAP_PRESET_ID = 'vector_amap_preset';

/** 拼接天地图瓦片服务 URL。 */
export const buildTiandituUrl = (pathAndQuery: string, tiandituTk: string): string => {
    const hasQuery = pathAndQuery.includes('?');
    const separator = hasQuery ? '&' : '?';
    return `https://${TILE_HOSTS.tianditu}${pathAndQuery}${separator}tk=${tiandituTk}`;
};

const createTiandituSource = (pathAndQuery: string, tiandituTk: string) => prioritizeTileSourceRequest(new XYZ({
    url: buildTiandituUrl(pathAndQuery, tiandituTk)
}));

const createAmapSource = (url: string) => prioritizeTileSourceRequest(new XYZ({ url }));

const BASEMAP_LAYER_DEFINITIONS: LayerSourceDefinition[] = [
    {
        id: 'vector_amap',
        name: '高德地图(GCJ)',
        category: 'base',
        group: '矢量',
        createSource: () => createAmapSource('https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}')
    },
    {
        id: 'imagery_amap',
        name: '高德影像(GCJ)',
        category: 'base',
        group: '影像',
        createSource: () => createAmapSource('https://webst01.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}')
    },
    {
        id: 'vector_tianditu',
        name: '天地图矢量',
        category: 'base',
        group: '矢量',
        createSource: ({ tiandituTk }) => createTiandituSource('/vec_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=vec&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}', tiandituTk)
    },
    {
        id: 'label_tianditu_vector',
        name: '天地图矢量注记',
        category: 'label',
        group: '注记',
        createSource: ({ tiandituTk }) => createTiandituSource('/cva_w/wmts?SERVICE=WMTS&VERSION=1.0.0&REQUEST=GetTile&LAYER=cva&STYLE=default&FORMAT=tiles&TILEMATRIXSET=w&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}', tiandituTk)
    },
    {
        id: 'imagery_tianditu',
        name: '天地图影像',
        category: 'base',
        group: '影像',
        createSource: ({ tiandituTk }) => createTiandituSource('/img_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=img&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}', tiandituTk)
    },
    {
        id: 'label_tianditu',
        name: '天地图影像注记',
        category: 'label',
        group: '注记',
        createSource: ({ tiandituTk }) => createTiandituSource('/cia_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=cia&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}', tiandituTk)
    }
];

const BASEMAP_PRESETS: BasemapPresetDefinition[] = [
    { id: 'vector_amap_preset', label: '高德地图', stack: ['vector_amap'], overviewStack: ['vector_amap'] },
    { id: 'imagery_amap_preset', label: '高德影像', stack: ['imagery_amap'], overviewStack: ['imagery_amap'] },
    { id: 'vector_tianditu_preset', label: '天地图矢量', stack: ['vector_tianditu', 'label_tianditu_vector'] },
    { id: 'imagery_tianditu_preset', label: '天地图影像', stack: ['imagery_tianditu', 'label_tianditu'] }
];

const BASEMAP_LAYER_MAP = new Map(BASEMAP_LAYER_DEFINITIONS.map((item) => [item.id, item]));
const BASEMAP_PRESET_MAP = new Map(BASEMAP_PRESETS.map((item) => [item.id, item]));

function resolveDefaultBasemapLayerIndex(): number {
    const index = BASEMAP_PRESETS.findIndex((preset) => preset.id === DEFAULT_BASEMAP_PRESET_ID);
    return index >= 0 ? index : 0;
}

function resolveDefaultVisibleLayerIdSet(): Set<string> {
    return new Set(resolvePresetLayerIds(DEFAULT_BASEMAP_PRESET_ID));
}

/** 默认底图在 URL_LAYER_OPTIONS 中的索引。 */
export const DEFAULT_BASEMAP_LAYER_INDEX = resolveDefaultBasemapLayerIndex();

const DEFAULT_VISIBLE_LAYER_ID_SET = resolveDefaultVisibleLayerIdSet();

/** URL 图层选项列表：用于 URL 参数中的图层索引映射。 */
export const URL_LAYER_OPTIONS = BASEMAP_PRESETS.map((preset) => preset.id);

/** 预设底图选项列表（用于 UI 下拉菜单）。 */
export const BASEMAP_OPTIONS = BASEMAP_PRESETS.map((preset) => ({
    value: preset.id,
    label: preset.label
}));

/** 获取一个 option 对应的真实图层堆叠（去重，保序）。 */
export function resolvePresetLayerIds(optionId: string): string[] {
    const preset = BASEMAP_PRESET_MAP.get(String(optionId || ''));
    const stack = Array.isArray(preset?.stack) && preset.stack.length
        ? preset.stack
        : [String(optionId || '')];

    const deduped: string[] = [];
    const seen = new Set<string>();

    stack.forEach((id) => {
        const normalized = String(id || '').trim();
        if (!normalized || seen.has(normalized)) return;
        if (!BASEMAP_LAYER_MAP.has(normalized)) return;

        seen.add(normalized);
        deduped.push(normalized);
    });

    return deduped;
}

/** 获取鹰眼视图要使用的图层堆叠，默认跟随当前底图预设。 */
export function resolveOverviewLayerIds(optionId: string): string[] {
    const preset = BASEMAP_PRESET_MAP.get(String(optionId || ''));
    const overviewStack = Array.isArray(preset?.overviewStack) && preset.overviewStack.length
        ? preset.overviewStack
        : preset?.stack;

    const layerIds = Array.isArray(overviewStack) && overviewStack.length
        ? overviewStack
        : resolvePresetLayerIds(optionId);

    const deduped: string[] = [];
    const seen = new Set<string>();

    layerIds.forEach((id) => {
        const normalized = String(id || '').trim();
        if (!normalized || seen.has(normalized)) return;
        if (!BASEMAP_LAYER_MAP.has(normalized)) return;

        seen.add(normalized);
        deduped.push(normalized);
    });

    if (deduped.length) return deduped;
    return resolvePresetLayerIds(DEFAULT_BASEMAP_PRESET_ID);
}

/** 获取 option 的展示名称。 */
export function getBasemapOptionLabel(optionId: string): string {
    const preset = BASEMAP_PRESET_MAP.get(String(optionId || ''));
    return preset?.label || String(optionId || '');
}

/** 获取图层分类（用于外部状态同步）。 */
export function getLayerCategory(layerId: string): LayerCategory {
    return BASEMAP_LAYER_MAP.get(String(layerId || ''))?.category || 'base';
}

/** 获取图层分组（用于外部状态同步）。 */
export function getLayerGroup(layerId: string): LayerGroup {
    return BASEMAP_LAYER_MAP.get(String(layerId || ''))?.group || '矢量';
}

/** 创建底图配置列表（由本文件集中配置驱动）。 */
export function createLayerConfigs(tiandituTk: string = '') {
    const context: LayerFactoryContext = { tiandituTk };

    return BASEMAP_LAYER_DEFINITIONS.map((definition) => ({
        id: definition.id,
        name: definition.name,
        category: definition.category,
        group: definition.group,
        visible: DEFAULT_VISIBLE_LAYER_ID_SET.has(definition.id),
        createSource: () => definition.createSource(context)
    }));
}

/** 导出主要管理功能。 */
export function useBasemapManager() {
    return {
        buildTiandituUrl,
        createLayerConfigs,
        resolvePresetLayerIds,
        resolveOverviewLayerIds,
        getBasemapOptionLabel,
        getLayerCategory,
        getLayerGroup
    };
}
