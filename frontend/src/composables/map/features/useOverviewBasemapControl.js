import { watch } from 'vue';

/**
 * Eagle-eye/overview map basemap controller.
 *
 * The overview map uses the same basemap registry as the main map, so provider
 * changes do not leave a hidden second set of tile URLs behind.
 */
export function createOverviewBasemapControl({
    selectedLayerRef,
    layerConfigs,
    resolveOverviewLayerIds,
    OverviewMapClass,
    TileLayerClass,
    className = 'ol-overviewmap ol-custom-overviewmap',
    collapseLabel = '«',
    label = '»',
    collapsed = false
}) {
    const configById = new Map(
        (Array.isArray(layerConfigs) ? layerConfigs : [])
            .map((config) => [String(config?.id || '').trim(), config])
            .filter(([id, config]) => id && config?.createSource)
    );

    let overviewControl = null;
    let stopSelectedLayerWatch = null;

    function createTileLayer(layerId, zIndex) {
        const config = configById.get(String(layerId || '').trim());
        const source = config?.createSource?.();
        if (!source || !TileLayerClass) return null;

        return new TileLayerClass({
            source,
            zIndex
        });
    }

    function createOverviewLayers(optionId) {
        const layerIds = resolveOverviewLayerIds?.(optionId) || [];
        const layers = layerIds
            .map((layerId, index) => createTileLayer(layerId, index))
            .filter(Boolean);

        if (layers.length) return layers;

        return Array.from(configById.keys())
            .slice(0, 1)
            .map((layerId, index) => createTileLayer(layerId, index))
            .filter(Boolean);
    }

    function replaceOverviewLayers(optionId) {
        const overviewMap = overviewControl?.getOverviewMap?.();
        const layerCollection = overviewMap?.getLayers?.();
        if (!layerCollection) return;

        layerCollection.clear();
        createOverviewLayers(optionId).forEach((layer) => overviewMap.addLayer(layer));
        overviewMap.renderSync?.();
    }

    function createControl(initialOptionId = selectedLayerRef?.value) {
        if (!OverviewMapClass) return null;

        overviewControl = new OverviewMapClass({
            className,
            layers: createOverviewLayers(initialOptionId),
            collapseLabel,
            label,
            collapsed
        });

        stopSelectedLayerWatch?.();
        stopSelectedLayerWatch = selectedLayerRef
            ? watch(selectedLayerRef, (optionId) => {
                replaceOverviewLayers(optionId);
            }, { flush: 'post' })
            : null;

        return overviewControl;
    }

    function dispose() {
        stopSelectedLayerWatch?.();
        stopSelectedLayerWatch = null;
        overviewControl = null;
    }

    return {
        createControl,
        refreshOverviewBasemap: replaceOverviewLayers,
        dispose
    };
}
